from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.project_memory import config
from tools.project_memory.services.index_project import index_project
from tools.project_memory.services.search import search


class ConfigSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_config(self):
        path = self.root / '.project-memory/config.yaml'
        path.parent.mkdir()
        path.write_text('version: 7\nindexing:\n  auto_index:\n    enabled: false\n  include_extensions: [.scss]\nvector:\n  backend: fallback\n')
        return path

    def test_existing_config_without_yaml_fails_closed(self):
        path = self.write_config()
        original = path.read_bytes()
        with patch.object(config, 'yaml', None):
            with self.assertRaisesRegex(RuntimeError, 'PyYAML.*interpreter'):
                config.load_config(self.root)
        self.assertEqual(path.read_bytes(), original)

    def test_search_and_index_stop_before_traversal_or_database_write(self):
        path = self.write_config()
        original = path.read_bytes()
        with patch.object(config, 'yaml', None), \
                patch('tools.project_memory.services.search.ensure_fresh_index') as freshness, \
                patch('tools.project_memory.services.search.SQLiteGraphStore') as search_store, \
                patch('tools.project_memory.services.index_project.iter_indexable_files') as walker, \
                patch('tools.project_memory.services.index_project.SQLiteGraphStore') as index_store:
            for operation in (lambda: search(self.root, 'query'), lambda: index_project(self.root, 'changed')):
                with self.assertRaisesRegex(RuntimeError, 'PyYAML'):
                    operation()
            freshness.assert_not_called()
            walker.assert_not_called()
            search_store.assert_not_called()
            index_store.assert_not_called()
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.root / '.project-memory/graph.sqlite').exists())

    def test_no_config_initialization_retains_defaults_without_yaml(self):
        with patch.object(config, 'yaml', None):
            self.assertEqual(config.load_config(self.root), config.DEFAULT_CONFIG)

    def test_available_yaml_loads_actual_config(self):
        if config.yaml is None:
            self.skipTest('PyYAML unavailable in test interpreter')
        self.write_config()
        loaded = config.load_config(self.root)
        self.assertFalse(loaded['indexing']['auto_index']['enabled'])
        self.assertEqual(loaded['indexing']['include_extensions'], ['.scss'])


if __name__ == '__main__':
    unittest.main()
