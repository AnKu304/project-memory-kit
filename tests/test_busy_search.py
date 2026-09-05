from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.services.concurrency import MemoryBusyError
from tools.project_memory.services.search import search
from tools.project_memory.vector.qdrant_store import QdrantLocalStore, VectorBackendBusyError


class BusySearchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.graph = SQLiteGraphStore(self.root, self.root / '.project-memory/graph.sqlite')
        self.graph.initialize()
        self.graph.upsert_chunk('auth.py', 'auth.session', 1, 2, 'Authentication session refresh')
        self.addCleanup(patch.stopall)
        patch('tools.project_memory.services.search.ensure_fresh_index', return_value=None).start()
        self.cfg = {'vector': {'backend': 'qdrant'}}
        patch('tools.project_memory.services.search.load_config', return_value=self.cfg).start()
        embedder = Mock()
        embedder.embed.return_value = [0.1, 0.2]
        patch('tools.project_memory.vector.qdrant_store.FastEmbedEmbeddings', return_value=embedder).start()
        self.client_factory = Mock()
        patch.dict(sys.modules, {'qdrant_client': types.SimpleNamespace(QdrantClient=self.client_factory),
                                'qdrant_client.models': types.SimpleNamespace(Filter=types.SimpleNamespace)}).start()

    def busy_lock(self):
        lock = Mock()
        lock.__enter__ = Mock(side_effect=MemoryBusyError('fixture local lock'))
        lock.__exit__ = Mock()
        patch('tools.project_memory.vector.qdrant_store.MemoryResourceLock', return_value=lock).start()

    def test_strict_busy_constructor_preserves_lexical_results_and_diagnostics(self):
        self.busy_lock()
        rows = search(self.root, 'session')
        self.assertIsInstance(rows, list)
        self.assertEqual(rows[0]['path'], 'auth.py')
        self.assertIn('busy', ' '.join(rows.diagnostics).lower())
        self.assertEqual(rows[0]['source'], 'hybrid')

    def test_auto_busy_constructor_exposes_diagnostics_with_zero_results(self):
        self.cfg['vector']['backend'] = 'auto'
        self.busy_lock()
        rows = search(self.root, 'nomatchingword')
        self.assertEqual(rows, [])
        self.assertIn('semantic', ' '.join(rows.diagnostics).lower())

    def test_busy_query_closes_client_and_keeps_results(self):
        self.client_factory.return_value.collection_exists.side_effect = MemoryBusyError('fixture busy read')
        rows = search(self.root, 'session')
        self.assertTrue(rows)
        self.assertTrue(rows.diagnostics)
        self.client_factory.return_value.close.assert_called_once()

    def test_native_storage_lock_signature_is_busy_only_for_local(self):
        self.client_factory.side_effect = RuntimeError(
            'Storage folder .project-memory/qdrant is already accessed by another instance of Qdrant client.'
        )
        rows = search(self.root, 'session')
        self.assertTrue(rows)
        self.assertTrue(rows.diagnostics)
        self.cfg['vector']['url'] = 'http://fixture.invalid'
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            search(self.root, 'session')

    def test_auto_index_busy_returns_existing_results_without_second_lock_wait(self):
        with patch('tools.project_memory.services.search.ensure_fresh_index', side_effect=VectorBackendBusyError('busy')):
            rows = search(self.root, 'session')
        self.assertTrue(rows)
        self.assertIn('stale', ' '.join(rows.diagnostics))
        self.client_factory.assert_not_called()
        with patch('tools.project_memory.services.search.ensure_fresh_index', side_effect=RuntimeError('nonbusy index failure')):
            with self.assertRaisesRegex(RuntimeError, 'nonbusy index failure'):
                search(self.root, 'session')

    def test_busy_query_points_and_legacy_search_are_reported(self):
        client = self.client_factory.return_value
        client.collection_exists.return_value = True
        client.query_points.side_effect = MemoryBusyError('fixture busy query')
        self.assertTrue(search(self.root, 'session').diagnostics)
        client.query_points.side_effect = AttributeError('old client')
        client.search.side_effect = MemoryBusyError('fixture busy legacy query')
        self.assertTrue(search(self.root, 'session').diagnostics)

    def test_nonbusy_constructor_error_still_raises(self):
        self.client_factory.side_effect = RuntimeError('fixture bad configuration')
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            search(self.root, 'session')

    def test_nonbusy_query_error_still_raises(self):
        self.client_factory.return_value.collection_exists.side_effect = RuntimeError('fixture corruption')
        with self.assertRaisesRegex(RuntimeError, 'search failed'):
            search(self.root, 'session')

    def test_strict_constructor_and_write_remain_errors(self):
        self.busy_lock()
        with self.assertRaises(RuntimeError):
            QdrantLocalStore(self.root / 'vectors', backend='qdrant', root=self.root)
        with patch('tools.project_memory.vector.qdrant_store.MemoryResourceLock'):
            store = QdrantLocalStore(self.root / 'other', backend='qdrant', root=self.root)
            with patch.object(store, '_upsert_qdrant', side_effect=MemoryBusyError('fixture busy write')):
                with self.assertRaisesRegex(RuntimeError, 'upsert failed'):
                    store.upsert_chunk('new', 'new', {})
            store.close()

    def test_cli_and_mcp_expose_busy_even_with_no_results(self):
        from tools.project_memory.cli import command_search
        from tools.project_memory.mcp import _tool_search, _tool_search_debug
        self.busy_lock()
        args = argparse.Namespace(query='nomatchingword', limit=10, layer=None, debug=False)
        output = io.StringIO()
        with patch('tools.project_memory.cli.root', return_value=self.root), redirect_stdout(output):
            self.assertEqual(command_search(args), 0)
        self.assertIn('busy', output.getvalue().lower())
        for handler in (_tool_search, _tool_search_debug):
            response = handler(self.root, {'query': 'nomatchingword'})
            self.assertFalse(response['isError'])
            self.assertEqual(response['structuredContent']['results'], [])
            self.assertTrue(response['structuredContent']['diagnostics'])
            self.assertIn('busy', response['content'][0]['text'].lower())


if __name__ == '__main__':
    unittest.main()
