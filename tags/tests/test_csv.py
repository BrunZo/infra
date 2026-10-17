import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tags.core.tag import App, Tag, TagAlias, TagEdge
from tags.core.tag_dag import TagDag
from tags.data.csv import init
from tags.data.protocol import TagAccess


class CsvTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "store"
        self.store: TagAccess = init(self.path)

    def seed(self):
        with self.store.transaction() as tx:
            for name in ("work", "coding", "python", "personal"):
                self.store.insert_tag(tx, name)
            self.store.insert_edge(tx, child_name="coding", parent_name="work")
            self.store.insert_edge(tx, child_name="python", parent_name="coding")
            self.store.insert_alias(tx, "dev", "timer", "coding")

    def contents(self):
        return {path.name: path.read_bytes() for path in self.path.glob("*.csv")}

    def test_initialization_creates_headers_and_preserves_existing_data(self):
        self.assertEqual(
            set(self.contents()), {"tags.csv", "edges.csv", "aliases.csv", "apps.csv"}
        )
        self.seed()
        before = self.contents()
        init(self.path)
        self.assertEqual(self.contents(), before)

    def test_insert_queries_and_reopen(self):
        self.seed()
        store = init(self.path)
        with store.transaction() as tx:
            self.assertEqual(store.tag(tx, "coding").name, "coding")
            self.assertIsNone(store.tag(tx, "missing"))
            self.assertEqual(
                [
                    tag.name
                    for tag in store.list_tags(
                        tx, ["python", "missing", "work", "work"]
                    )
                ],
                ["python", "work"],
            )
            self.assertEqual(
                [tag.name for tag in store.tag_children(tx, "work")], ["coding"]
            )
            self.assertEqual(
                [tag.name for tag in store.tag_parents(tx, "python")], ["coding"]
            )
            self.assertEqual(store.tag_children(tx, "missing"), [])
            self.assertEqual(store.tag_parents(tx, "missing"), [])
            self.assertEqual(store.resolve_tag(tx, "dev", "timer").name, "coding")
            self.assertEqual(store.translate_tag(tx, "coding", "timer"), "dev")
            alias = store.list_aliases(tx, "timer")[0]
            self.assertEqual((alias.app.name, alias.tag.name), ("timer", "coding"))
            self.assertEqual(store.list_aliases(tx, "missing"), [])
            self.assertIsNone(store.resolve_tag(tx, "missing", "timer"))
            self.assertIsNone(store.resolve_tag(tx, "dev", "missing"))
            self.assertIsNone(store.translate_tag(tx, "missing", "timer"))
            self.assertIsNone(store.translate_tag(tx, "coding", "missing"))

    def test_identical_inserts_are_noops(self):
        self.seed()
        with patch.object(self.store, "_write", wraps=self.store._write) as write:
            with self.store.transaction() as tx:
                self.store.insert_tag(tx, "coding")
                self.store.insert_edge(tx, child_name="coding", parent_name="work")
                self.store.insert_alias(tx, "dev", "timer", "coding")
            write.assert_not_called()

    def test_alias_uniqueness_and_application_scope(self):
        self.seed()
        with self.store.transaction() as tx:
            with self.assertRaises(ValueError):
                self.store.insert_alias(tx, "dev", "timer", "python")
            with self.assertRaises(ValueError):
                self.store.insert_alias(tx, "another", "timer", "coding")
            self.store.insert_alias(tx, "dev", "editor", "python")
            self.assertEqual(self.store.resolve_tag(tx, "dev", "timer").name, "coding")
            self.assertEqual(self.store.resolve_tag(tx, "dev", "editor").name, "python")

    def test_missing_references_do_not_create_records(self):
        with self.store.transaction() as tx:
            with self.assertRaises(ValueError):
                self.store.insert_edge(tx, "missing", "also missing")
            with self.assertRaises(ValueError):
                self.store.insert_alias(tx, "dev", "timer", "missing")
            dag = self.store.load_dag(tx)
            self.assertEqual(
                (dag.tags, dag.edges, dag.aliases, dag.apps), ([], [], [], [])
            )

    def test_cycles_are_rejected_without_modifying_pending_changes(self):
        self.seed()
        with self.store.transaction() as tx:
            with self.assertRaises(ValueError):
                self.store.insert_edge(tx, child_name="work", parent_name="python")
            with self.assertRaises(ValueError):
                self.store.insert_edge(tx, child_name="coding", parent_name="coding")
            self.assertEqual(len(self.store.load_dag(tx).edges), 2)
            self.store.insert_edge(tx, child_name="python", parent_name="work")

    def test_delete_tag_cascades_without_deleting_descendants(self):
        self.seed()
        with self.store.transaction() as tx:
            self.store.delete_tag(tx, "coding")
            self.store.delete_tag(tx, "coding")
        with self.store.transaction() as tx:
            dag = self.store.load_dag(tx)
            self.assertEqual(
                {tag.name for tag in dag.tags}, {"work", "python", "personal"}
            )
            self.assertEqual(dag.edges, [])
            self.assertEqual(dag.aliases, [])
            self.assertEqual([app.name for app in dag.apps], ["timer"])
            self.store.insert_edge(tx, child_name="python", parent_name="work")

    def test_delete_edge_and_alias_are_idempotent_and_allow_reinsertion(self):
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

    def test_exception_rolls_back_every_table(self):
        self.seed()
        before = self.contents()
        with self.assertRaisesRegex(RuntimeError, "abort"):
            with self.store.transaction() as tx:
                self.store.insert_tag(tx, "new")
                self.store.delete_tag(tx, "coding")
                self.store.insert_alias(tx, "n", "another app", "new")
                raise RuntimeError("abort")
        self.assertEqual(self.contents(), before)

    def test_dump_round_trip_preserves_ids_and_relationships(self):
        dag = TagDag(
            tags=[Tag(id=10, name="parent"), Tag(id=20, name="child")],
            edges=[TagEdge(id=30, parent_id=10, child_id=20)],
            aliases=[TagAlias(id=40, app_id=50, tag_id=20, alias="c")],
            apps=[App(id=50, name="app")],
        )
        with self.store.transaction() as tx:
            self.store.dump_dag(tx, dag)
            dag.tags[0].name = "outside change"
        reopened = init(self.path)
        with reopened.transaction() as tx:
            snapshot = reopened.load_dag(tx)
            self.assertEqual(
                [(tag.id, tag.name) for tag in snapshot.tags],
                [(10, "parent"), (20, "child")],
            )
            self.assertEqual(snapshot.edges[0].parent.name, "parent")
            self.assertEqual(snapshot.edges[0].child.name, "child")
            self.assertEqual(snapshot.aliases[0].app.name, "app")
            self.assertEqual(snapshot.aliases[0].tag.name, "child")

    def test_invalid_dump_keeps_current_state(self):
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
            for dag in invalid:
                with self.subTest(dag=dag), self.assertRaises(ValueError):
                    self.store.dump_dag(tx, dag)
                self.assertEqual(len(self.store.load_dag(tx).tags), 4)

    def test_read_results_cannot_mutate_transaction(self):
        self.seed()
        before = self.contents()
        with self.store.transaction() as tx:
            self.store.tag(tx, "coding").name = "changed"
            self.store.list_tags(tx, ["coding"])[0].name = "changed"
            self.store.tag_children(tx, "work")[0].name = "changed"
            self.store.tag_parents(tx, "python")[0].name = "changed"
            self.store.list_aliases(tx, "timer")[0].alias = "changed"
            self.store.resolve_tag(tx, "dev", "timer").name = "changed"
            self.store.load_dag(tx).tags.clear()
        self.assertEqual(self.contents(), before)

    def test_csv_quoting_and_unicode(self):
        name = 'café, "work"\nsecond line'
        alias = 'alias, "quoted"\nnext'
        with self.store.transaction() as tx:
            self.store.insert_tag(tx, name)
            self.store.insert_alias(tx, alias, "aplicación", name)
        with self.store.transaction() as tx:
            self.assertEqual(self.store.resolve_tag(tx, alias, "aplicación").name, name)

    def test_transaction_lifecycle_and_ownership(self):
        tx = self.store.transaction()
        with self.assertRaises(RuntimeError):
            self.store.insert_tag(tx, "before entry")
        with tx:
            with self.assertRaises(RuntimeError):
                tx.__enter__()
            with self.assertRaises(ValueError):
                init(self.path).tag(tx, "anything")
        with self.assertRaises(RuntimeError):
            self.store.tag(tx, "after exit")
        with self.assertRaises(RuntimeError):
            tx.__enter__()

    def test_stale_transaction_does_not_overwrite_a_committed_change(self):
        with self.assertRaisesRegex(RuntimeError, "changed during"):
            with self.store.transaction() as outer:
                self.store.insert_tag(outer, "outer")
                other = init(self.path)
                with other.transaction() as inner:
                    other.insert_tag(inner, "inner")
        with self.store.transaction() as tx:
            self.assertIsNone(self.store.tag(tx, "outer"))
            self.assertIsNotNone(self.store.tag(tx, "inner"))

    def test_batch_writes_each_changed_table_once(self):
        with patch.object(self.store, "_write", wraps=self.store._write) as write:
            with self.store.transaction() as tx:
                for index in range(100):
                    self.store.insert_tag(tx, f"tag {index}")
            write.assert_called_once()
            self.assertEqual(set(write.call_args.args[0]), {"tags"})

    def test_malformed_files_are_rejected(self):
        with self.subTest("header"):
            (self.path / "tags.csv").write_text("wrong,header\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                with self.store.transaction():
                    pass
        for row in ("not-an-int,name", "1", "1,name,extra", "1,a\n1,b"):
            with self.subTest(row=row):
                (self.path / "tags.csv").write_text(
                    f"id,name\n{row}\n", encoding="utf-8"
                )
                with self.assertRaises(ValueError):
                    with self.store.transaction():
                        pass

    def test_temporary_files_are_cleaned_up_when_serialization_fails(self):
        before = self.contents()
        with patch.object(
            csv.DictWriter, "writerows", side_effect=OSError("disk full")
        ):
            with self.assertRaises(OSError):
                with self.store.transaction() as tx:
                    self.store.insert_tag(tx, "pending")
        self.assertEqual(self.contents(), before)
        self.assertEqual(list(self.path.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
