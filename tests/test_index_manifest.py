from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.project_memory.services import index_project as indexing
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.hashing import sha256_file
from tools.project_memory.vector.qdrant_store import QdrantLocalStore


class IndexManifestTests(unittest.TestCase):
    def test_unchanged_index_does_not_open_vector_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'app.py').write_text('def run():\n    return 1\n')
            with patch.object(indexing, 'QdrantLocalStore', side_effect=lambda *a, **k:
                              QdrantLocalStore(*a, **{**k, 'backend': 'fallback'})):
                indexing.index_project(root, 'full')
            with patch.object(indexing, 'QdrantLocalStore', side_effect=AssertionError('unneeded backend')):
                self.assertIn('skipped=1', indexing.index_project(root, 'changed'))

    def test_changed_mode_includes_index_stale_file_outside_git_diff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('alpha', 'beta'):
                (root / f'{name}.py').write_text(f'def {name}():\n    return 1\n')
            with patch.object(indexing, 'QdrantLocalStore', side_effect=lambda *a, **k:
                              QdrantLocalStore(*a, **{**k, 'backend': 'fallback'})):
                indexing.index_project(root, 'full')
                # alpha represents a committed/pulled change absent from git diff,
                # while beta is a separate uncommitted change.
                for name in ('alpha', 'beta'):
                    (root / f'{name}.py').write_text(f'def {name}():\n    return 2\n')
                with patch('tools.project_memory.git_diff.changed_files', return_value=['beta.py']), patch(
                    'tools.project_memory.git_diff.untracked_files', return_value=[]
                ):
                    report = indexing.index_project(root, 'changed')
            self.assertIn('indexed=2', report)
            store = SQLiteGraphStore(root, root / '.project-memory/graph.sqlite')
            for name in ('alpha', 'beta'):
                self.assertEqual(store.file_hash(f'{name}.py'), sha256_file(root / f'{name}.py'))


if __name__ == '__main__':
    unittest.main()
