import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import event, inspect
from sqlalchemy.exc import IntegrityError, OperationalError

from tags.core.tag import Tag, TagAlias, TagEdge
from tags.core.tag_dag import TagDag
from tags.data.csv import init as init_csv
from tags.data.protocol import TagAccess
from tags.data.sqlite3 import init


class SQLiteTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "nested" / "tags.db"
        self.store: TagAccess = init(self.path)

    def seed(self):
        with self.store.transaction() as tx:
            for name in ("work", "coding", "python", "personal"):
                self.store.insert_tag(tx, name)
            self.store.insert_edge(tx, child_name="coding", parent_name="work")
            self.store.insert_edge(tx, child_name="python", parent_name="coding")
            self.store.insert_alias(tx, "dev", "timer", "coding")

    def snapshot(self, store=None):
        store = self.store if store is None else store
        with store.transaction() as tx:
            dag = store.load_dag(tx)
        return {
            "tags": [(tag.id, tag.name) for tag in dag.tags],
            "edges": [(edge.id, edge.parent_id, edge.child_id) for edge in dag.edges],
            "aliases": [
                (alias.id, alias.app_id, alias.alias, alias.tag_id)
                for alias in dag.aliases
            ],
            "apps": [(app.id, app.name) for app in dag.apps],
        }

    def test_initialization_and_reopening_preserve_data(self):
        self.assertTrue(self.path.is_file())
        self.assertEqual(
            self.snapshot(), {"tags": [], "edges": [], "aliases": [], "apps": []}
        )
        self.seed()
        self.assertEqual(self.snapshot(init(self.path)), self.snapshot())

    def test_queries_and_relationships(self):
        self.seed()
        with self.store.transaction() as tx:
            self.assertEqual(self.store.tag(tx, "coding").name, "coding")
            self.assertIsNone(self.store.tag(tx, "missing"))
            self.assertEqual(
                [
                    tag.name
                    for tag in self.store.list_tags(
                        tx, ["python", "missing", "work", "work"]
                    )
                ],
                ["python", "work"],
            )
            self.assertEqual(self.store.list_tags(tx, []), [])
            self.assertEqual(
                [tag.name for tag in self.store.tag_children(tx, "work")], ["coding"]
            )
            self.assertEqual(
                [tag.name for tag in self.store.tag_parents(tx, "python")], ["coding"]
            )
            self.assertEqual(self.store.tag_children(tx, "missing"), [])
            self.assertEqual(self.store.tag_parents(tx, "missing"), [])
            self.assertEqual(self.store.resolve_tag(tx, "dev", "timer").name, "coding")
            self.assertEqual(self.store.translate_tag(tx, "coding", "timer"), "dev")
            alias = self.store.list_aliases(tx, "timer")[0]
            self.assertEqual((alias.app.name, alias.tag.name), ("timer", "coding"))
            self.assertEqual(self.store.list_aliases(tx, "missing"), [])
            self.assertIsNone(self.store.resolve_tag(tx, "missing", "timer"))
            self.assertIsNone(self.store.resolve_tag(tx, "dev", "missing"))
            self.assertIsNone(self.store.translate_tag(tx, "missing", "timer"))
            self.assertIsNone(self.store.translate_tag(tx, "coding", "missing"))

    def test_duplicate_inserts_and_alias_conflicts(self):
        self.seed()
        before = self.snapshot()
        with self.store.transaction() as tx:
            self.store.insert_tag(tx, "coding")
            self.store.insert_edge(tx, child_name="coding", parent_name="work")
            self.store.insert_alias(tx, "dev", "timer", "coding")
            with self.assertRaises(ValueError):
                self.store.insert_alias(tx, "dev", "timer", "python")
            with self.assertRaises(ValueError):
                self.store.insert_alias(tx, "other", "timer", "coding")
        self.assertEqual(self.snapshot(), before)
        with self.store.transaction() as tx:
            self.store.insert_alias(tx, "dev", "editor", "python")
            self.assertEqual(self.store.resolve_tag(tx, "dev", "editor").name, "python")

    def test_missing_references_leave_no_records(self):
        before = self.snapshot()
        with self.store.transaction() as tx:
            with self.assertRaises(ValueError):
                self.store.insert_edge(tx, "missing", "other")
            with self.assertRaises(ValueError):
                self.store.insert_alias(tx, "alias", "new app", "missing")
        self.assertEqual(self.snapshot(), before)

    def test_cycle_checks_include_pending_edges_and_preserve_the_transaction(self):
        with self.store.transaction() as tx:
            for name in ("a", "b", "c", "d"):
                self.store.insert_tag(tx, name)
            self.store.insert_edge(tx, child_name="b", parent_name="a")
            self.store.insert_edge(tx, child_name="c", parent_name="a")
            self.store.insert_edge(tx, child_name="d", parent_name="b")
            self.store.insert_edge(tx, child_name="d", parent_name="c")
            for child, parent in (("a", "d"), ("a", "b"), ("b", "b")):
                with (
                    self.subTest(child=child, parent=parent),
                    self.assertRaises(ValueError),
                ):
                    self.store.insert_edge(tx, child_name=child, parent_name=parent)
            self.store.insert_edge(tx, child_name="d", parent_name="a")
            self.assertEqual(len(self.store.load_dag(tx).edges), 5)

    def test_deep_graph_and_large_tag_query(self):
        count = 1200
        dag = TagDag(
            tags=[Tag(id=index, name=f"tag {index}") for index in range(count)],
            edges=[
                TagEdge(id=index, parent_id=index - 1, child_id=index)
                for index in range(1, count)
            ],
            aliases=[],
            apps=[],
        )
        with self.store.transaction() as tx:
            self.store.dump_dag(tx, dag)
            with self.assertRaises(ValueError):
                self.store.insert_edge(
                    tx, child_name="tag 0", parent_name=f"tag {count - 1}"
                )
            names = [f"tag {index}" for index in reversed(range(count))]
            self.assertEqual(
                [tag.name for tag in self.store.list_tags(tx, names)], names
            )

    def test_tag_deletion_cascades_without_deleting_descendants_or_apps(self):
        self.seed()
        with self.store.transaction() as tx:
            self.store.delete_tag(tx, "coding")
            self.store.delete_tag(tx, "coding")
            dag = self.store.load_dag(tx)
            self.assertEqual(
                {tag.name for tag in dag.tags}, {"work", "python", "personal"}
            )
            self.assertEqual(dag.edges, [])
            self.assertEqual(dag.aliases, [])
            self.assertEqual([app.name for app in dag.apps], ["timer"])

    def test_edge_and_alias_deletion_are_idempotent(self):
        self.seed()
        with self.store.transaction() as tx:
            for _ in range(2):
                self.store.delete_edge(tx, "work", "coding")
                self.store.delete_edge(tx, "missing", "coding")
                self.store.delete_alias(tx, "dev", "timer")
                self.store.delete_alias(tx, "dev", "missing")
            self.assertEqual(self.store.tag_children(tx, "work"), [])
            self.assertIsNone(self.store.translate_tag(tx, "coding", "timer"))
            self.store.insert_edge(tx, child_name="coding", parent_name="work")
            self.store.insert_alias(tx, "new", "timer", "coding")

    def test_exception_rolls_back_all_tables(self):
        self.seed()
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "abort"), self.store.transaction() as tx:
            self.store.delete_tag(tx, "coding")
            self.store.insert_tag(tx, "new")
            self.store.insert_alias(tx, "alias", "new app", "new")
            raise RuntimeError("abort")
        self.assertEqual(self.snapshot(), before)

    def test_dump_round_trip_with_csv_preserves_ids_and_relationships(self):
        self.seed()
        csv_store = init_csv(Path(self.directory.name) / "csv")
        with self.store.transaction() as tx:
            dag = self.store.load_dag(tx)
        with csv_store.transaction() as tx:
            csv_store.dump_dag(tx, dag)
        self.assertEqual(self.snapshot(csv_store), self.snapshot())
        with csv_store.transaction() as tx:
            dag = csv_store.load_dag(tx)
        with self.store.transaction() as tx:
            self.store.dump_dag(tx, dag)
            dag.tags[0].name = "outside change"
        self.assertEqual(self.snapshot(csv_store), self.snapshot())
        with self.store.transaction() as tx:
            dag = self.store.load_dag(tx)
        self.assertEqual(dag.edges[0].parent.name, "work")
        self.assertEqual(dag.edges[0].child.name, "coding")
        self.assertEqual(dag.aliases[0].app.name, "timer")
        self.assertEqual(dag.aliases[0].tag.name, "coding")

    def test_invalid_dumps_preserve_earlier_pending_work(self):
        self.seed()
        invalid = [
            TagDag([Tag(id=1, name="a"), Tag(id=1, name="b")], [], [], []),
            TagDag([Tag(id=1, name="a"), Tag(id=2, name="a")], [], [], []),
            TagDag(
                [Tag(id=1, name="a")], [TagEdge(id=1, parent_id=1, child_id=2)], [], []
            ),
            TagDag(
                [Tag(id=1, name="a")], [TagEdge(id=1, parent_id=1, child_id=1)], [], []
            ),
            TagDag(
                [Tag(id=1, name="a")],
                [],
                [TagAlias(id=1, app_id=2, tag_id=1, alias="a")],
                [],
            ),
            TagDag([Tag(name="no ID")], [], [], []),
        ]
        with self.store.transaction() as tx:
            self.store.insert_tag(tx, "pending")
            for dag in invalid:
                with self.subTest(dag=dag), self.assertRaises(ValueError):
                    self.store.dump_dag(tx, dag)
                self.assertEqual(len(self.store.load_dag(tx).tags), 5)

    def test_dump_database_failure_rolls_back_to_savepoint(self):
        self.seed()
        with self.store.transaction() as tx:
            self.store.insert_tag(tx, "earlier pending change")
            connection = self.store._connection(tx)
            connection.exec_driver_sql(
                """
                CREATE TEMP TRIGGER fail_dump BEFORE INSERT ON tag
                WHEN NEW.name = 'reject'
                BEGIN SELECT RAISE(ABORT, 'injected failure'); END
                """
            )
            with self.assertRaisesRegex(ValueError, "injected failure"):
                self.store.dump_dag(
                    tx, TagDag([Tag(id=100, name="reject")], [], [], [])
                )
            self.assertIsNotNone(self.store.tag(tx, "earlier pending change"))
            self.assertEqual(len(self.store.load_dag(tx).tags), 5)
            self.store.insert_tag(tx, "later change")
        self.assertEqual(len(self.snapshot()["tags"]), 6)

    def test_successful_dump_is_still_rolled_back_with_outer_transaction(self):
        self.seed()
        before = self.snapshot()
        with self.assertRaises(RuntimeError):
            with self.store.transaction() as tx:
                self.store.dump_dag(tx, TagDag([], [], [], []))
                raise RuntimeError("abort")
        self.assertEqual(self.snapshot(), before)

    def test_read_results_are_detached(self):
        self.seed()
        before = self.snapshot()
        with self.store.transaction() as tx:
            tag = self.store.tag(tx, "coding")
            self.assertTrue(inspect(tag).detached)
            tag.name = "changed"
            self.store.list_tags(tx, ["coding"])[0].name = "changed"
            self.store.tag_children(tx, "work")[0].name = "changed"
            self.store.tag_parents(tx, "python")[0].name = "changed"
            alias = self.store.list_aliases(tx, "timer")[0]
            for record in (alias, alias.tag, alias.app):
                self.assertTrue(inspect(record).detached)
            alias.alias = "changed"
            self.store.resolve_tag(tx, "dev", "timer").name = "changed"
            dag = self.store.load_dag(tx)
            for record in (*dag.tags, *dag.edges, *dag.aliases, *dag.apps):
                self.assertTrue(inspect(record).detached)
            dag.tags.clear()
        self.assertEqual(self.snapshot(), before)

    def test_quoting_unicode_and_sql_parameters(self):
        name = "caf\u00e9, 'work'\n'); DROP TABLE tag; --"
        alias = 'alias, "quoted"\nnext'
        with self.store.transaction() as tx:
            self.store.insert_tag(tx, name)
            self.store.insert_alias(tx, alias, "aplicaci\u00f3n", name)
        with self.store.transaction() as tx:
            self.assertEqual(
                self.store.resolve_tag(tx, alias, "aplicaci\u00f3n").name, name
            )
            self.assertEqual(self.store.list_tags(tx, [name])[0].name, name)

    def test_transaction_lifecycle_and_ownership(self):
        other = init(self.path)
        tx = self.store.transaction()
        with self.assertRaises(RuntimeError):
            self.store.tag(tx, "before entry")
        with tx:
            with self.assertRaises(RuntimeError):
                tx.__enter__()
            with self.assertRaises(ValueError):
                other.tag(tx, "wrong store")
        with self.assertRaises(RuntimeError):
            self.store.tag(tx, "after exit")
        with self.assertRaises(RuntimeError):
            tx.__enter__()

    def test_begin_immediate_blocks_a_second_writer(self):
        self.seed()
        other = init(self.path)

        def impatient_connection(dbapi_connection, connection_record):
            dbapi_connection.execute("PRAGMA busy_timeout = 1")

        event.listen(other.engine, "connect", impatient_connection)

        with self.store.transaction() as tx:
            self.store.insert_edge(tx, child_name="personal", parent_name="python")
            with self.assertRaisesRegex(OperationalError, "locked"):
                with other.transaction():
                    self.fail("Second writer acquired the transaction")
        with other.transaction() as tx:
            with self.assertRaises(ValueError):
                other.insert_edge(tx, child_name="work", parent_name="personal")

    def test_database_constraints_and_foreign_keys_are_enabled(self):
        self.seed()
        with self.store.transaction() as tx:
            connection = self.store._connection(tx)
            self.assertEqual(
                connection.exec_driver_sql("PRAGMA foreign_keys").scalar(), 1
            )
            edge = self.store.load_dag(tx).edges[0]
            for sql, parameters in (
                (
                    "INSERT INTO tag_edge (parent_id, child_id) VALUES (?, ?)",
                    (edge.parent_id, edge.child_id),
                ),
                (
                    "INSERT INTO tag_edge (parent_id, child_id) VALUES (?, ?)",
                    (edge.parent_id, edge.parent_id),
                ),
                (
                    "INSERT INTO tag_edge (parent_id, child_id) VALUES (?, ?)",
                    (999, edge.child_id),
                ),
            ):
                with (
                    self.subTest(sql=sql, parameters=parameters),
                    self.assertRaises(IntegrityError),
                ):
                    connection.exec_driver_sql(sql, parameters)


if __name__ == "__main__":
    unittest.main()
