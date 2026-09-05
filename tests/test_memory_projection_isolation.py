from pathlib import Path
import tempfile
import unittest

from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.services.index_project import _cleanup_removed_files


class MemoryProjectionIsolationTests(unittest.TestCase):
    def test_source_cleanup_preserves_durable_memory_projection(self):
        for removed in (False, True):
            for kind in ('KnowledgeChunk', 'RationaleChunk'):
                with self.subTest(removed=removed, kind=kind), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    store = SQLiteGraphStore(root, root / '.project-memory/graph.sqlite')
                    store.initialize()
                    path = '.project-memory/knowledge/research/note.md'
                    note = root / path
                    note.parent.mkdir(parents=True, exist_ok=True)
                    note.write_text('Durable finding')
                    store.upsert_node(kind='File', path=path, name='note.md')
                    module = store.upsert_node(kind='Module', path=path, name='source_module')
                    manual = store.upsert_node(kind=kind, path=path, name='durable')
                    generated = store.upsert_chunk(path, path, 1, 1, 'source projection')
                    with store.connect() as conn:
                        conn.execute('INSERT INTO chunks_fts VALUES (?, ?, ?, ?)',
                                     (manual, path, 'durable', 'Durable finding'))
                    store.update_file_state(path, 'old-source-hash', 'text', [])
                    if removed:
                        # Legacy indexes could include the note in the general
                        # source manifest; the new walker excludes own memory.
                        _cleanup_removed_files(root, store, [])
                    else:
                        store.clear_generated_file_memory(path)
                    self.assertTrue(store.query('SELECT id FROM nodes WHERE id=?', (manual,)))
                    self.assertTrue(store.query('SELECT chunk_id FROM chunks_fts WHERE chunk_id=?', (manual,)))
                    self.assertFalse(store.query('SELECT chunk_id FROM chunks_fts WHERE chunk_id=?', (generated,)))
                    self.assertIsNone(store.file_hash(path))
                    self.assertEqual(note.read_text(), 'Durable finding')
                    if removed:
                        self.assertFalse(store.query('SELECT id FROM nodes WHERE id=?', (module,)))


if __name__ == '__main__':
    unittest.main()
