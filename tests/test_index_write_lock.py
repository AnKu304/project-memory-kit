"""Native indexing must respect the writer that owns an in-flight graph pass."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.project_memory import mcp
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.services import index_project as indexing
from tools.project_memory.services.concurrency import MemoryWriteLock, write_lock_path
from tools.project_memory.vector.qdrant_store import QdrantLocalStore


class NativeIndexWriteLockTests(unittest.TestCase):
    def test_native_index_releases_lock_after_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def fail(*args, **kwargs):
                self.assertTrue(write_lock_path(root).exists())
                raise RuntimeError('binding failed')
            with patch.object(mcp, 'index_project', side_effect=fail):
                response = mcp._handle_tool_call(root, 1, {
                    'name': 'pmem_index', 'arguments': {'mode': 'changed'}})
            self.assertTrue(response['result']['isError'])
            self.assertIn('binding failed', str(response))
            self.assertFalse(write_lock_path(root).exists())

    def test_native_index_cannot_invalidate_another_writers_binding_targets(self):
        for change in ('update', 'delete'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / 'source.py'
                source.write_text('def original():\n    return 1\n')
                (root / 'caller.py').write_text('def caller():\n    return 1\n')
                with patch.object(indexing, 'QdrantLocalStore', side_effect=lambda *a, **k:
                                  QdrantLocalStore(*a, **{**k, 'backend': 'fallback'})):
                    indexing.index_project(root, 'full')
                    store = SQLiteGraphStore(root, root / '.project-memory/graph.sqlite')
                    # A CLI/auto-index writer has read its post-file binding targets.
                    with MemoryWriteLock(root, 'auto-index binding'):
                        target = store.query("SELECT id FROM nodes WHERE kind='Symbol' AND name='original'")[0]['id']
                        caller = store.query("SELECT id FROM nodes WHERE kind='Symbol' AND name='caller'")[0]['id']
                        if change == 'update':
                            source.write_text('def renamed():\n    return 2\n')
                        else:
                            source.unlink()
                        with store.connect() as connection:
                            before = list(connection.iterdump())
                        vector_path = root / '.project-memory/qdrant/fallback_chunks.jsonl'
                        before_vectors = vector_path.read_bytes()
                        response = mcp._handle_tool_call(root, 1, {
                            'name': 'pmem_index', 'arguments': {'mode': 'changed'}})
                        with store.connect() as connection:
                            self.assertEqual(list(connection.iterdump()), before)
                        self.assertEqual(vector_path.read_bytes(), before_vectors)
                        # Without native locking, its cleanup removes target here,
                        # and the existing writer fails with FOREIGN KEY constraint.
                        store.upsert_edge(caller, target, 'REFERENCES', source='binding')
                        self.assertTrue(response['result']['isError'])
                        self.assertIn('write lock is busy', str(response))
                        self.assertTrue(write_lock_path(root).exists())
                    self.assertFalse(write_lock_path(root).exists())
                    response = mcp._handle_tool_call(root, 2, {
                        'name': 'pmem_index', 'arguments': {'mode': 'changed'}})
                    self.assertFalse(response['result'].get('isError', False))
                    self.assertFalse(store.query('SELECT id FROM nodes WHERE id=?', (target,)))
                    self.assertFalse(store.query('PRAGMA foreign_key_check'))
                    self.assertFalse(write_lock_path(root).exists())


if __name__ == '__main__':
    unittest.main()
