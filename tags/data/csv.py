"""AI-generated: implementation of protocol.py for CSV files."""

import csv
from collections import deque
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import TracebackType
from typing import Self

from tags.core.tag import App, Tag, TagAlias, TagEdge
from tags.core.tag_dag import TagDag
from tags.data.protocol import Transaction

_TABLES = {
    "tags": (Tag, ("id", "name")),
    "edges": (TagEdge, ("id", "parent_id", "child_id")),
    "aliases": (TagAlias, ("id", "app_id", "alias", "tag_id")),
    "apps": (App, ("id", "name")),
}


def _index(records, key, label):
    result = {}
    for record in records:
        value = key(record)
        if value in result:
            raise ValueError(f"Duplicate {label}: {value!r}")
        result[value] = record
    return result


class _State:
    def __init__(self, dag: TagDag):
        tables = {}
        for name, (model, fields) in _TABLES.items():
            records = []
            for record in getattr(dag, name):
                values = {field: getattr(record, field) for field in fields}
                for field, value in values.items():
                    expected = str if field in ("name", "alias") else int
                    if type(value) is not expected:
                        raise ValueError(f"Invalid {name}.{field}: {value!r}")
                records.append(model(**values))
            tables[name] = records
            _index(records, lambda record: record.id, f"{name} ID")

        self._next_ids = {
            name: max((record.id for record in records), default=0) + 1
            for name, records in tables.items()
        }
        self.tags = _index(tables["tags"], lambda tag: tag.name, "tag name")
        self.tags_by_id = {tag.id: tag for tag in self.tags.values()}
        self.apps = _index(tables["apps"], lambda app: app.name, "app name")
        self.apps_by_id = {app.id: app for app in self.apps.values()}
        self.edges = _index(
            tables["edges"], lambda edge: (edge.parent_id, edge.child_id), "edge"
        )
        self.aliases = _index(
            tables["aliases"], lambda alias: (alias.app_id, alias.alias), "alias"
        )
        self.translations = _index(
            tables["aliases"],
            lambda alias: (alias.app_id, alias.tag_id),
            "translation",
        )
        for edge in self.edges.values():
            if (
                edge.parent_id not in self.tags_by_id
                or edge.child_id not in self.tags_by_id
            ):
                raise ValueError(f"Edge {edge.id} references a missing tag")
        for alias in self.aliases.values():
            if (
                alias.tag_id not in self.tags_by_id
                or alias.app_id not in self.apps_by_id
            ):
                raise ValueError(f"Alias {alias.id} references a missing tag or app")
        self.children = {tag_id: set() for tag_id in self.tags_by_id}
        for parent_id, child_id in self.edges:
            self.children[parent_id].add(child_id)
        self._validate_acyclic()

    def allocate_id(self, table: str) -> int:
        value = self._next_ids[table]
        self._next_ids[table] += 1
        return value

    def _validate_acyclic(self) -> None:
        children = {tag_id: [] for tag_id in self.tags_by_id}
        incoming = dict.fromkeys(self.tags_by_id, 0)
        for parent_id, child_id in self.edges:
            children[parent_id].append(child_id)
            incoming[child_id] += 1
        pending = deque(tag_id for tag_id, count in incoming.items() if count == 0)
        visited = 0
        while pending:
            parent_id = pending.popleft()
            visited += 1
            for child_id in children[parent_id]:
                incoming[child_id] -= 1
                if incoming[child_id] == 0:
                    pending.append(child_id)
        if visited != len(self.tags):
            raise ValueError("Tag edges must form a directed acyclic graph")

    def rows(self) -> dict[str, list[dict]]:
        tables = {
            "tags": self.tags.values(),
            "edges": self.edges.values(),
            "aliases": self.aliases.values(),
            "apps": self.apps.values(),
        }
        return {
            name: [
                {field: getattr(record, field) for field in _TABLES[name][1]}
                for record in sorted(records, key=lambda record: record.id)
            ]
            for name, records in tables.items()
        }

    def dag(self) -> TagDag:
        rows = self.rows()
        tables = {
            name: [model(**row) for row in rows[name]]
            for name, (model, _) in _TABLES.items()
        }
        tags = {tag.id: tag for tag in tables["tags"]}
        apps = {app.id: app for app in tables["apps"]}
        for edge in tables["edges"]:
            edge.parent = tags[edge.parent_id]
            edge.child = tags[edge.child_id]
        for alias in tables["aliases"]:
            alias.tag = tags[alias.tag_id]
            alias.app = apps[alias.app_id]
        return TagDag(**tables)

    def alias_copy(self, alias: TagAlias) -> TagAlias:
        tag = self.tags_by_id[alias.tag_id]
        app = self.apps_by_id[alias.app_id]
        return TagAlias(
            id=alias.id,
            alias=alias.alias,
            tag_id=tag.id,
            app_id=app.id,
            tag=Tag(id=tag.id, name=tag.name),
            app=App(id=app.id, name=app.name),
        )


class CsvTransaction:
    def __init__(self, store: CsvTagAccess):
        self._store = store
        self._state: _State | None = None
        self._initial: dict[str, list[dict]] | None = None
        self._used = False

    def __enter__(self) -> Self:
        if self._used:
            raise RuntimeError("A transaction can only be entered once")
        self._used = True
        self._state = self._store._read()
        self._initial = self._state.rows()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        state = self._store._state(self)
        try:
            if exc_type is None:
                initial = self._initial
                if initial is None:
                    raise RuntimeError("Transaction has no initial snapshot")
                rows = state.rows()
                changed = {
                    name: records
                    for name, records in rows.items()
                    if records != initial[name]
                }
                if changed:
                    if self._store._read().rows() != initial:
                        raise RuntimeError("CSV store changed during the transaction")
                    self._store._write(changed)
        finally:
            self._state = None


class CsvTagAccess:
    def __init__(self, csv_dir: Path):
        self.csv_dir = Path(csv_dir)
        self.csv_dir.mkdir(parents=True, exist_ok=True)
        self._write({name: [] for name in _TABLES if not self._path(name).exists()})

    def _path(self, name: str) -> Path:
        return self.csv_dir / f"{name}.csv"

    def _read(self) -> _State:
        tables = {}
        for name, (model, fields) in _TABLES.items():
            with self._path(name).open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames != list(fields):
                    raise ValueError(f"Invalid CSV header in {self._path(name)}")
                records = []
                for line, row in enumerate(reader, start=2):
                    try:
                        if None in row or any(value is None for value in row.values()):
                            raise ValueError("Incorrect number of columns")
                        values = {
                            field: row[field]
                            if field in ("name", "alias")
                            else int(row[field])
                            for field in fields
                        }
                        records.append(model(**values))
                    except (TypeError, ValueError) as exc:
                        raise ValueError(
                            f"Invalid row in {self._path(name)}:{line}"
                        ) from exc
                tables[name] = records
        return _State(TagDag(**tables))

    def _write(self, tables: dict[str, list[dict]]) -> None:
        temporary = {}
        try:
            for name, rows in tables.items():
                with NamedTemporaryFile(
                    mode="w",
                    newline="",
                    encoding="utf-8",
                    dir=self.csv_dir,
                    prefix=f".{name}.",
                    suffix=".tmp",
                    delete=False,
                ) as stream:
                    temporary[name] = Path(stream.name)
                    writer = csv.DictWriter(stream, fieldnames=_TABLES[name][1])
                    writer.writeheader()
                    writer.writerows(rows)
            for name, path in temporary.items():
                path.replace(self._path(name))
        finally:
            for path in temporary.values():
                path.unlink(missing_ok=True)

    def _state(self, transaction: Transaction) -> _State:
        if (
            not isinstance(transaction, CsvTransaction)
            or transaction._store is not self
        ):
            raise ValueError("Transaction belongs to a different store")
        if transaction._state is None:
            raise RuntimeError("Transaction is not active")
        return transaction._state

    def transaction(self) -> CsvTransaction:
        return CsvTransaction(self)

    def load_dag(self, transaction: Transaction) -> TagDag:
        return self._state(transaction).dag()

    def dump_dag(self, transaction: Transaction, dag: TagDag) -> None:
        self._state(transaction)
        state = _State(dag)
        assert isinstance(transaction, CsvTransaction)
        transaction._state = state

    def insert_tag(self, transaction: Transaction, tag_name: str) -> None:
        state = self._state(transaction)
        if tag_name not in state.tags:
            tag = Tag(id=state.allocate_id("tags"), name=tag_name)
            state.tags[tag_name] = tag
            state.tags_by_id[tag.id] = tag
            state.children[tag.id] = set()

    def insert_edge(
        self, transaction: Transaction, child_name: str, parent_name: str
    ) -> None:
        state = self._state(transaction)
        try:
            parent = state.tags[parent_name]
            child = state.tags[child_name]
        except KeyError as exc:
            raise ValueError(f"Unknown tag: {exc.args[0]!r}") from exc
        key = (parent.id, child.id)
        if key in state.edges:
            return
        pending = [child.id]
        visited = set()
        while pending:
            tag_id = pending.pop()
            if tag_id == parent.id:
                raise ValueError("Tag edges must form a directed acyclic graph")
            if tag_id not in visited:
                visited.add(tag_id)
                pending.extend(state.children[tag_id])
        state.edges[key] = TagEdge(
            id=state.allocate_id("edges"), parent_id=parent.id, child_id=child.id
        )
        state.children[parent.id].add(child.id)

    def insert_alias(
        self, transaction: Transaction, tag_alias: str, app_name: str, tag_name: str
    ) -> None:
        state = self._state(transaction)
        if tag_name not in state.tags:
            raise ValueError(f"Unknown tag: {tag_name!r}")
        tag = state.tags[tag_name]
        app = state.apps.get(app_name)
        if app is None:
            app = App(id=state.allocate_id("apps"), name=app_name)
        existing = state.aliases.get((app.id, tag_alias))
        if existing is not None:
            if existing.tag_id == tag.id:
                return
            raise ValueError(
                f"Alias {tag_alias!r} already maps to another tag in {app_name!r}"
            )
        if (app.id, tag.id) in state.translations:
            raise ValueError(f"Tag {tag_name!r} already has an alias in {app_name!r}")
        alias = TagAlias(
            id=state.allocate_id("aliases"),
            app_id=app.id,
            alias=tag_alias,
            tag_id=tag.id,
        )
        state.apps[app.name] = app
        state.apps_by_id[app.id] = app
        state.aliases[(app.id, tag_alias)] = alias
        state.translations[(app.id, tag.id)] = alias

    def delete_tag(self, transaction: Transaction, tag_name: str) -> None:
        state = self._state(transaction)
        tag = state.tags.pop(tag_name, None)
        if tag is None:
            return
        del state.tags_by_id[tag.id]
        del state.children[tag.id]
        for key in list(state.edges):
            if tag.id in key:
                del state.edges[key]
                if key[0] != tag.id:
                    state.children[key[0]].discard(tag.id)
        for key, alias in list(state.aliases.items()):
            if alias.tag_id == tag.id:
                del state.aliases[key]
                del state.translations[(alias.app_id, alias.tag_id)]

    def delete_edge(
        self, transaction: Transaction, parent_tag_name: str, child_tag_name: str
    ) -> None:
        state = self._state(transaction)
        parent = state.tags.get(parent_tag_name)
        child = state.tags.get(child_tag_name)
        if parent is not None and child is not None:
            state.edges.pop((parent.id, child.id), None)
            state.children[parent.id].discard(child.id)

    def delete_alias(
        self, transaction: Transaction, tag_alias: str, app_name: str
    ) -> None:
        state = self._state(transaction)
        app = state.apps.get(app_name)
        if app is not None:
            alias = state.aliases.pop((app.id, tag_alias), None)
            if alias is not None:
                del state.translations[(app.id, alias.tag_id)]

    def tag(self, transaction: Transaction, tag_name: str) -> Tag | None:
        tag = self._state(transaction).tags.get(tag_name)
        return None if tag is None else Tag(id=tag.id, name=tag.name)

    def list_tags(self, transaction: Transaction, tag_name: list[str]) -> list[Tag]:
        state = self._state(transaction)
        return [
            Tag(id=tag.id, name=tag.name)
            for name in dict.fromkeys(tag_name)
            if (tag := state.tags.get(name)) is not None
        ]

    def tag_children(self, transaction: Transaction, tag_name: str) -> list[Tag]:
        state = self._state(transaction)
        tag = state.tags.get(tag_name)
        if tag is None:
            return []
        return [
            Tag(id=child.id, name=child.name)
            for parent_id, child_id in state.edges
            if parent_id == tag.id
            for child in (state.tags_by_id[child_id],)
        ]

    def tag_parents(self, transaction: Transaction, tag_name: str) -> list[Tag]:
        state = self._state(transaction)
        tag = state.tags.get(tag_name)
        if tag is None:
            return []
        return [
            Tag(id=parent.id, name=parent.name)
            for parent_id, child_id in state.edges
            if child_id == tag.id
            for parent in (state.tags_by_id[parent_id],)
        ]

    def list_aliases(self, transaction: Transaction, app_name: str) -> list[TagAlias]:
        state = self._state(transaction)
        app = state.apps.get(app_name)
        if app is None:
            return []
        return [
            state.alias_copy(alias)
            for alias in state.aliases.values()
            if alias.app_id == app.id
        ]

    def resolve_tag(
        self, transaction: Transaction, tag_alias: str, app_name: str
    ) -> Tag | None:
        state = self._state(transaction)
        app = state.apps.get(app_name)
        alias = None if app is None else state.aliases.get((app.id, tag_alias))
        if alias is None:
            return None
        tag = state.tags_by_id[alias.tag_id]
        return Tag(id=tag.id, name=tag.name)

    def translate_tag(
        self, transaction: Transaction, tag_name: str, app_name: str
    ) -> str | None:
        state = self._state(transaction)
        app = state.apps.get(app_name)
        tag = state.tags.get(tag_name)
        if app is None or tag is None:
            return None
        alias = state.translations.get((app.id, tag.id))
        return None if alias is None else alias.alias


def init(csv_dir: Path) -> CsvTagAccess:
    return CsvTagAccess(csv_dir)
