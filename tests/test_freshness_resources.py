from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.hashing import sha256_file
from tools.project_memory.ignore import is_binary
from tools.project_memory.services.auto_index import index_freshness


class FreshnessResourcesTest(unittest.TestCase):
    def test_binary_probe_reads_only_the_existing_2048_byte_sample(self):
        path = Path("fixture.dat")
        stream = io.BytesIO(b"x" * 2048 + b"\0")
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded read")), \
             mock.patch.object(Path, "open", return_value=stream) as opened, \
             mock.patch.object(stream, "read", wraps=stream.read) as read:
            self.assertFalse(is_binary(path))
            opened.assert_called_once_with("rb")
            read.assert_called_once_with(2048)
        self.assertTrue(stream.closed)

    def test_binary_probe_keeps_null_empty_and_unreadable_behavior(self):
        for content, expected in [(b"", False), (b"hello", False), (b"x\0", True)]:
            with self.subTest(content=content), mock.patch.object(Path, "open", return_value=io.BytesIO(content)):
                self.assertEqual(is_binary(Path("fixture.dat")), expected)
        with mock.patch.object(Path, "open", side_effect=PermissionError("fixture")):
            self.assertTrue(is_binary(Path("fixture.dat")))

    def test_freshness_uses_bounded_connections_without_caching_file_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = SQLiteGraphStore(root, root / ".project-memory/graph.sqlite")
            store.initialize()
            files = []
            for i in range(20):
                path = root / f"file_{i:02}.py"
                path.write_text("a = 1\n", encoding="utf-8")
                files.append(path)
                store.update_file_state(path.name, sha256_file(path), "fixture", [])
            original = SQLiteGraphStore.connect
            connections = []

            def connect(instance):
                connection = original(instance)
                connections.append(connection)
                return connection

            try:
                with mock.patch.object(SQLiteGraphStore, "connect", connect):
                    self.assertTrue(index_freshness(root).fresh)
                self.assertLessEqual(len(connections), 2, "one schema setup plus one manifest read")
            finally:
                for connection in connections:
                    connection.close()
            files[0].write_text("a = 2\n", encoding="utf-8")
            files[1].unlink()
            (root / "new.py").write_text("new = True\n", encoding="utf-8")
            changed = index_freshness(root)
            self.assertEqual((changed.missing_files, changed.stale_files, changed.removed_files), (1, 1, 1))
            self.assertFalse(changed.fresh)
            # No cache: same-size edits, additions and deletions remain visible.
            self.assertEqual(set(changed.sample), {files[0].name, files[1].name, "new.py"})


if __name__ == "__main__":
    unittest.main()
