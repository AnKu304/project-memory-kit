from pathlib import Path
import sqlite3
import tempfile
import unittest
from tools.project_memory.services.memory_overview import memory_overview
from tools.project_memory.services.knowledge import _store


class MemoryOverviewTests(unittest.TestCase):
    def test_missing_database_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = memory_overview(root, limit=2)
            self.assertFalse(result['filesystem_checked'])
            self.assertEqual(result['status'], 'missing')
            self.assertEqual(list(root.iterdir()), [])

    def test_bounded_deterministic_samples_and_independent_axes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = _store(root)
            for i in range(5):
                store.upsert_node(kind='File', path=f'{i}.py', name=str(i), properties={
                    'memory_scope': 'project', 'memory_type': 'code',
                    'memory_domain': 'backend', 'memory_audience': 'project'})
            first = memory_overview(root, limit=2)
            self.assertEqual(first, memory_overview(root, limit=2))
            self.assertEqual(len(first['files']), 2)
            self.assertTrue(first['truncated']['files'])
            self.assertEqual(first['axes']['memory_domain'], [{'value': 'backend', 'count': 5}])
            self.assertFalse(first['filesystem_checked'])

    def test_rejects_database_outside_project(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            _store(Path(outside))
            (root / '.project-memory').mkdir()
            (root / '.project-memory/graph.sqlite').symlink_to(Path(outside) / '.project-memory/graph.sqlite')
            with self.assertRaises(ValueError):
                memory_overview(root)

    def test_legacy_database_and_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / '.project-memory/graph.sqlite'
            path.parent.mkdir()
            conn = sqlite3.connect(path)
            try:
                conn.execute('CREATE TABLE nodes(kind TEXT, path TEXT, properties_json TEXT)')
                conn.execute("INSERT INTO nodes VALUES ('File','old.md','{}')")
                conn.commit()
            finally:
                conn.close()
            result = memory_overview(root)
            self.assertEqual(result['axes']['memory_domain'], [{'value': 'unclassified', 'count': 1}])
            self.assertEqual(result['entries'], [])
            for limit in (0, 101, True, 2.5):
                with self.assertRaises(ValueError):
                    memory_overview(root, limit)

    def test_entry_relation_samples_are_capped(self):
        from unittest.mock import patch
        from tools.project_memory.services.knowledge import add_knowledge
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'note.md').write_text('Note')
            with patch('tools.project_memory.services.knowledge._index_entry'):
                for i in range(4):
                    add_knowledge(root, 'research', f'Note {i}', 'note.md', links=['git:abc'])
            result = memory_overview(root, limit=2)
            self.assertEqual(result['counts']['knowledge'], 4)
            self.assertEqual(len(result['entries']), 2)
            self.assertEqual(len(result['relations']), 2)
            self.assertTrue(result['truncated']['entries'])
            self.assertTrue(result['truncated']['relations'])
