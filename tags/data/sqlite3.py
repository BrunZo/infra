"""AI-generated: implementation of protocol.py for SQLite3."""

from collections import deque
from contextlib import closing, contextmanager
from pathlib import Path
from types import TracebackType
from typing import Self

from sqlalchemy import (
    URL,
    create_engine,
    delete,
    event,
    exists,
    insert,
    literal,
    select,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.pool import NullPool

from tags.core.tag import App, Base, Tag, TagAlias, TagEdge
from tags.core.tag_dag import TagDag
from tags.data.protocol import Transaction

_MODELS = {
    "tags": Tag,
    "edges": TagEdge,
    "aliases": TagAlias,
    "apps": App,
}


def _prepare_dag(dag: TagDag) -> dict[str, list[dict]]:
    tables = {}
    for name, model in _MODELS.items():
        fields = model.__table__.columns.keys()
        rows = []
        ids = set()
        for record in getattr(dag, name):
            row = {field: getattr(record, field) for field in fields}
            for field, value in row.items():
                expected = str if field in ("name", "alias") else int
                if type(value) is not expected:
                    raise ValueError(f"Invalid {name}.{field}: {value!r}")
            if row["id"] in ids:
                raise ValueError(f"Duplicate {name} ID: {row['id']}")
            ids.add(row["id"])
            rows.append(row)
        tables[name] = rows

    for name, fields in (
        ("tags", ("name",)),
        ("apps", ("name",)),
        ("edges", ("parent_id", "child_id")),
        ("aliases", ("app_id", "alias")),
        ("aliases", ("app_id", "tag_id")),
    ):
        keys = [tuple(row[field] for field in fields) for row in tables[name]]
        if len(set(keys)) != len(keys):
            raise ValueError(f"Duplicate {name} key: {fields}")

    children = {row["id"]: [] for row in tables["tags"]}
    incoming = dict.fromkeys(children, 0)
    app_ids = {row["id"] for row in tables["apps"]}
    for edge in tables["edges"]:
        parent_id, child_id = edge["parent_id"], edge["child_id"]
        if parent_id not in children or child_id not in children:
            raise ValueError(f"Edge {edge['id']} references a missing tag")
        children[parent_id].append(child_id)
        incoming[child_id] += 1
    for alias in tables["aliases"]:
        if alias["tag_id"] not in children or alias["app_id"] not in app_ids:
            raise ValueError(f"Alias {alias['id']} references a missing tag or app")

    pending = deque(tag_id for tag_id, count in incoming.items() if count == 0)
    visited = 0
    while pending:
        tag_id = pending.popleft()
        visited += 1
        for child_id in children[tag_id]:
            incoming[child_id] -= 1
            if incoming[child_id] == 0:
                pending.append(child_id)
    if visited != len(children):
        raise ValueError("Tag edges must form a directed acyclic graph")
    return tables


@contextmanager
def _savepoint(session: Session):
    try:
        with session.begin_nested():
            yield
    except IntegrityError as exc:
        raise ValueError(str(exc.orig)) from exc


class SQLiteTransaction:
    def __init__(self, store: SQLiteTagAccess):
        self._store = store
        self._session: Session | None = None
        self._used = False

    def __enter__(self) -> Self:
        if self._used:
            raise RuntimeError("A transaction can only be entered once")
        self._used = True
        session = Session(self._store.engine, expire_on_commit=False)
        try:
            session.connection()
        except BaseException:
            session.close()
            raise
        self._session = session
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._store._session(self)
        try:
            if exc_type is None:
                session.commit()
            else:
                session.rollback()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()
            self._session = None


class SQLiteTagAccess:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            URL.create("sqlite+pysqlite", database=str(self.db_path.resolve())),
            poolclass=NullPool,
        )
        event.listen(self.engine, "connect", self._configure_connection)
        event.listen(self.engine, "begin", self._begin_transaction)
        with self.engine.begin() as connection:
            Base.metadata.create_all(connection)

    @staticmethod
    def _configure_connection(dbapi_connection, connection_record) -> None:
        dbapi_connection.isolation_level = None
        with closing(dbapi_connection.cursor()) as cursor:
            cursor.execute("PRAGMA foreign_keys = ON")

    @staticmethod
    def _begin_transaction(connection: Connection) -> None:
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    def _session(self, transaction: Transaction) -> Session:
        if (
            not isinstance(transaction, SQLiteTransaction)
            or transaction._store is not self
        ):
            raise ValueError("Transaction belongs to a different store")
        if transaction._session is None:
            raise RuntimeError("Transaction is not active")
        return transaction._session

    def _connection(self, transaction: Transaction) -> Connection:
        return self._session(transaction).connection()

    def _records(self, transaction: Transaction, statement) -> list:
        session = self._session(transaction)
        records = list(session.scalars(statement))
        session.expunge_all()
        return records

    def transaction(self) -> SQLiteTransaction:
        return SQLiteTransaction(self)

    def load_dag(self, transaction: Transaction) -> TagDag:
        session = self._session(transaction)
        tables = {}
        for name, model in _MODELS.items():
            statement = select(model).order_by(model.id)
            if model is TagEdge:
                statement = statement.options(
                    joinedload(TagEdge.parent), joinedload(TagEdge.child)
                )
            elif model is TagAlias:
                statement = statement.options(
                    joinedload(TagAlias.tag), joinedload(TagAlias.app)
                )
            tables[name] = list(session.scalars(statement))
        session.expunge_all()
        return TagDag(**tables)

    def dump_dag(self, transaction: Transaction, dag: TagDag) -> None:
        session = self._session(transaction)
        tables = _prepare_dag(dag)
        with _savepoint(session):
            for name in ("aliases", "edges", "tags", "apps"):
                session.execute(delete(_MODELS[name]))
            for name in ("tags", "apps", "edges", "aliases"):
                if tables[name]:
                    session.execute(insert(_MODELS[name]), tables[name])

    def insert_tag(self, transaction: Transaction, tag_name: str) -> None:
        self._session(transaction).execute(
            sqlite_insert(Tag)
            .values(name=tag_name)
            .on_conflict_do_nothing(index_elements=[Tag.name])
        )

    def insert_edge(
        self, transaction: Transaction, child_name: str, parent_name: str
    ) -> None:
        session = self._session(transaction)
        parent_id = session.scalar(select(Tag.id).where(Tag.name == parent_name))
        child_id = session.scalar(select(Tag.id).where(Tag.name == child_name))
        if parent_id is None or child_id is None:
            missing = parent_name if parent_id is None else child_name
            raise ValueError(f"Unknown tag: {missing!r}")
        if (
            session.scalar(
                select(TagEdge.id).where(
                    TagEdge.parent_id == parent_id, TagEdge.child_id == child_id
                )
            )
            is not None
        ):
            return
        reachable = select(literal(child_id).label("id")).cte(
            "reachable", recursive=True
        )
        reachable = reachable.union(
            select(TagEdge.child_id).join(
                reachable, TagEdge.parent_id == reachable.c.id
            )
        )
        if session.scalar(select(exists().where(reachable.c.id == parent_id))):
            raise ValueError("Tag edges must form a directed acyclic graph")
        session.execute(insert(TagEdge).values(parent_id=parent_id, child_id=child_id))

    def insert_alias(
        self, transaction: Transaction, tag_alias: str, app_name: str, tag_name: str
    ) -> None:
        session = self._session(transaction)
        tag_id = session.scalar(select(Tag.id).where(Tag.name == tag_name))
        if tag_id is None:
            raise ValueError(f"Unknown tag: {tag_name!r}")
        with _savepoint(session):
            session.execute(
                sqlite_insert(App)
                .values(name=app_name)
                .on_conflict_do_nothing(index_elements=[App.name])
            )
            app_id = session.scalar(select(App.id).where(App.name == app_name))
            existing = session.scalar(
                select(TagAlias.tag_id).where(
                    TagAlias.app_id == app_id, TagAlias.alias == tag_alias
                )
            )
            if existing is not None:
                if existing == tag_id:
                    return
                raise ValueError(
                    f"Alias {tag_alias!r} already maps to another tag in {app_name!r}"
                )
            if (
                session.scalar(
                    select(TagAlias.id).where(
                        TagAlias.app_id == app_id, TagAlias.tag_id == tag_id
                    )
                )
                is not None
            ):
                raise ValueError(
                    f"Tag {tag_name!r} already has an alias in {app_name!r}"
                )
            session.execute(
                insert(TagAlias).values(app_id=app_id, alias=tag_alias, tag_id=tag_id)
            )

    def delete_tag(self, transaction: Transaction, tag_name: str) -> None:
        self._session(transaction).execute(delete(Tag).where(Tag.name == tag_name))

    def delete_edge(
        self, transaction: Transaction, parent_tag_name: str, child_tag_name: str
    ) -> None:
        self._session(transaction).execute(
            delete(TagEdge).where(
                TagEdge.parent_id
                == select(Tag.id).where(Tag.name == parent_tag_name).scalar_subquery(),
                TagEdge.child_id
                == select(Tag.id).where(Tag.name == child_tag_name).scalar_subquery(),
            )
        )

    def delete_alias(
        self, transaction: Transaction, tag_alias: str, app_name: str
    ) -> None:
        self._session(transaction).execute(
            delete(TagAlias).where(
                TagAlias.alias == tag_alias,
                TagAlias.app_id
                == select(App.id).where(App.name == app_name).scalar_subquery(),
            )
        )

    def tag(self, transaction: Transaction, tag_name: str) -> Tag | None:
        records = self._records(transaction, select(Tag).where(Tag.name == tag_name))
        return records[0] if records else None

    def list_tags(self, transaction: Transaction, tag_name: list[str]) -> list[Tag]:
        self._session(transaction)
        names = list(dict.fromkeys(tag_name))
        tags = {}
        for start in range(0, len(names), 900):
            records = self._records(
                transaction, select(Tag).where(Tag.name.in_(names[start : start + 900]))
            )
            tags.update((tag.name, tag) for tag in records)
        return [tags[name] for name in names if name in tags]

    def tag_children(self, transaction: Transaction, tag_name: str) -> list[Tag]:
        return self._records(
            transaction,
            select(Tag)
            .join(TagEdge, TagEdge.child_id == Tag.id)
            .where(
                TagEdge.parent_id
                == select(Tag.id).where(Tag.name == tag_name).scalar_subquery()
            )
            .order_by(TagEdge.id),
        )

    def tag_parents(self, transaction: Transaction, tag_name: str) -> list[Tag]:
        return self._records(
            transaction,
            select(Tag)
            .join(TagEdge, TagEdge.parent_id == Tag.id)
            .where(
                TagEdge.child_id
                == select(Tag.id).where(Tag.name == tag_name).scalar_subquery()
            )
            .order_by(TagEdge.id),
        )

    def list_aliases(self, transaction: Transaction, app_name: str) -> list[TagAlias]:
        return self._records(
            transaction,
            select(TagAlias)
            .join(TagAlias.app)
            .where(App.name == app_name)
            .options(joinedload(TagAlias.app), joinedload(TagAlias.tag))
            .order_by(TagAlias.id),
        )

    def resolve_tag(
        self, transaction: Transaction, tag_alias: str, app_name: str
    ) -> Tag | None:
        records = self._records(
            transaction,
            select(Tag)
            .join(TagAlias.tag)
            .join(TagAlias.app)
            .where(TagAlias.alias == tag_alias, App.name == app_name),
        )
        return records[0] if records else None

    def translate_tag(
        self, transaction: Transaction, tag_name: str, app_name: str
    ) -> str | None:
        return self._session(transaction).scalar(
            select(TagAlias.alias)
            .join(TagAlias.tag)
            .join(TagAlias.app)
            .where(Tag.name == tag_name, App.name == app_name)
        )


def init(db_path: Path) -> SQLiteTagAccess:
    return SQLiteTagAccess(db_path)
