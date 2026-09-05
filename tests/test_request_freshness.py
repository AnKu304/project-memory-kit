from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.project_memory.services import auto_index
from tools.project_memory.services.concurrency import MemoryBusyError
from tools.project_memory.services.test_selector import select_tests


FRESH = auto_index.IndexFreshness(1, 1, 0, 0, 0, ())
STALE = auto_index.IndexFreshness(1, 1, 0, 1, 0, ('app.py',))


class RequestFreshnessTests(unittest.TestCase):
    def test_reuses_only_within_request_and_keeps_project_roots_separate(self):
        @auto_index.reuse_request_freshness
        def request():
            for root in (Path('/fixture/a'), Path('/fixture/b')):
                for command in ('impact', 'search', 'search', 'tests'):
                    auto_index.ensure_fresh_index(root, command)

        with patch.object(auto_index, 'auto_index_enabled', return_value=True), patch.object(
            auto_index, 'index_freshness', return_value=FRESH
        ) as check:
            request()
            self.assertEqual(check.call_count, 2)
            request()
            self.assertEqual(check.call_count, 4)
            auto_index.ensure_fresh_index(Path('/fixture/a'), 'search')
            auto_index.ensure_fresh_index(Path('/fixture/a'), 'search')
            self.assertEqual(check.call_count, 6)

    def test_failed_request_drops_state(self):
        root = Path('/fixture/a')

        @auto_index.reuse_request_freshness
        def request():
            auto_index.ensure_fresh_index(root, 'search')
            raise ValueError('fixture')

        with patch.object(auto_index, 'auto_index_enabled', return_value=True), patch.object(
            auto_index, 'index_freshness', return_value=FRESH
        ) as check:
            with self.assertRaisesRegex(ValueError, 'fixture'):
                request()
            auto_index.ensure_fresh_index(root, 'search')
            self.assertEqual(check.call_count, 2)

    def test_busy_write_does_not_mark_index_fresh(self):
        @auto_index.reuse_request_freshness
        def request(root):
            self.assertIn('skipped', auto_index.ensure_fresh_index(root, 'search'))
            self.assertIn('skipped', auto_index.ensure_fresh_index(root, 'search'))

        with tempfile.TemporaryDirectory() as directory, patch.object(
            auto_index, 'auto_index_enabled', return_value=True
        ), patch.object(auto_index, 'index_freshness', return_value=STALE) as check, patch.object(
            auto_index, 'MemoryWriteLock', side_effect=MemoryBusyError('fixture')
        ):
            request(Path(directory))
            self.assertEqual(check.call_count, 2)

    def test_next_request_still_detects_same_size_edits(self):
        from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
        from tools.project_memory.hashing import sha256_file

        @auto_index.reuse_request_freshness
        def request(root):
            return auto_index.ensure_fresh_index(root, 'search')

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'app.py'
            source.write_text('a=1\n')
            store = SQLiteGraphStore(root, root / '.project-memory/graph.sqlite')
            store.initialize()
            store.update_file_state('app.py', sha256_file(source), 'fixture', [])
            self.assertIsNone(request(root))
            source.write_text('a=2\n')
            with patch.object(auto_index, 'MemoryWriteLock', side_effect=MemoryBusyError('fixture')):
                self.assertIn('skipped', request(root))

    def test_test_selection_uses_supplied_impact_without_repeating_analysis(self):
        impact = {'tests': [{'target': 'tests/test_app.py', 'reason': 'affected'}]}
        with patch('tools.project_memory.services.test_selector.analyze_impact', side_effect=AssertionError('duplicate')):
            self.assertEqual(select_tests(Path('/fixture'), impact=impact), ['python -m unittest tests/test_app.py'])

    def test_real_context_checks_freshness_once_without_merging_layer_searches(self):
        from tools.project_memory.services import context_builder
        from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
        from tools.project_memory.hashing import sha256_file
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'app.py'
            source.write_text('a=1\n')
            store = SQLiteGraphStore(root, root / '.project-memory/graph.sqlite')
            store.initialize()
            store.update_file_state('app.py', sha256_file(source), 'fixture', [])
            with patch.object(auto_index, 'index_freshness', wraps=auto_index.index_freshness) as checks, patch.object(
                context_builder, 'analyze_impact', wraps=context_builder.analyze_impact
            ) as impacts, patch('tools.project_memory.services.search._vector_search', return_value=[]) as vectors:
                context = context_builder.build_context(root, 'application design')
            self.assertEqual(checks.call_count, 1)
            self.assertEqual(impacts.call_count, 1)
            self.assertEqual(vectors.call_count, 3, 'independent general/knowledge/rationale retrieval preserved')
            self.assertIn('Retrieved Knowledge', context)
            self.assertIn('Retrieved Rationale', context)

    def test_busy_context_auto_index_is_bounded_and_reports_staleness(self):
        from tools.project_memory.vector.qdrant_store import VectorBackendBusyError

        @auto_index.reuse_request_freshness
        def context(root):
            for command in ('impact', 'search', 'search', 'tests'):
                auto_index.ensure_fresh_index(root, command)
            self.assertTrue(auto_index.request_vector_busy(root))
            return '# Context\n'

        with tempfile.TemporaryDirectory() as directory, patch.object(
            auto_index, 'auto_index_enabled', return_value=True
        ), patch.object(auto_index, 'index_freshness', return_value=STALE) as checks, patch(
            'tools.project_memory.services.index_project.index_project', side_effect=VectorBackendBusyError('fixture')
        ) as index:
            root = Path(directory)
            output = context(root)
            self.assertIn('may be stale', output)
            self.assertEqual(checks.call_count, 1)
            self.assertEqual(index.call_count, 1)
            self.assertFalse(auto_index.request_vector_busy(root))
            with self.assertRaises(VectorBackendBusyError):
                auto_index.ensure_fresh_index(root, 'search')

    def test_context_busy_is_reported_once_and_does_not_retry_per_layer(self):
        from tools.project_memory.services.context_builder import build_context
        from tools.project_memory.services.context_compiler import compile_context
        from tools.project_memory.vector.qdrant_store import VectorBackendBusyError
        for compiler in (build_context, compile_context):
            with self.subTest(compiler=compiler.__name__), tempfile.TemporaryDirectory() as directory, patch.object(
                auto_index, 'index_freshness', return_value=FRESH
            ), patch('tools.project_memory.services.search._vector_search', side_effect=VectorBackendBusyError('fixture')) as vector:
                root = Path(directory)
                output = compiler(root, 'design')
                self.assertEqual(vector.call_count, 1)
                self.assertIn('Semantic search unavailable', output)
                compiler(root, 'design')
                self.assertEqual(vector.call_count, 2, 'next request can retry the backend')

    def test_embedding_instances_and_query_vectors_are_request_root_model_scoped(self):
        import sys
        import types
        from unittest.mock import Mock
        from tools.project_memory.vector.qdrant_store import QdrantLocalStore
        clients = []
        def client_factory(**kwargs):
            client = Mock()
            clients.append(client)
            return client
        embedder = Mock()
        embedder.embed.return_value = [0.1, 0.2]

        @auto_index.reuse_request_freshness
        def context(root):
            for model in ('one', 'one', 'one', 'two'):
                vectors = QdrantLocalStore(root / 'vectors', backend='qdrant', root=root,
                                           model_name=model, url='http://fixture.invalid')
                self.assertEqual(vectors._embed_query('query'), [0.1, 0.2])
                vectors.close()
            fallback = QdrantLocalStore(root / 'fallback', backend='fallback', root=root,
                                        model_name='one', vector_size=3)
            self.assertEqual(len(fallback._embed_query('query')), 3)
            fallback.close()

        modules = {'qdrant_client': types.SimpleNamespace(QdrantClient=client_factory)}
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, modules), patch(
            'tools.project_memory.vector.qdrant_store.FastEmbedEmbeddings', return_value=embedder
        ) as factory:
            root = Path(directory)
            context(root)
            self.assertEqual(factory.call_count, 2, 'one embedder per model in this request')
            self.assertEqual(embedder.embed.call_count, 2)
            self.assertTrue(all(client.close.call_count == 1 for client in clients))
            context(root)
            self.assertEqual(factory.call_count, 4, 'nothing retained across context calls')

    def test_request_resources_have_a_hard_entry_bound_and_do_not_mix_roots(self):
        created = []
        def factory():
            value = object()
            created.append(value)
            return value

        @auto_index.reuse_request_freshness
        def context():
            left = auto_index.request_resource(Path('/a'), ('model',), factory)
            right = auto_index.request_resource(Path('/b'), ('model',), factory)
            self.assertIsNot(left, right)
            self.assertIs(left, auto_index.request_resource(Path('/a'), ('model',), factory))
            for i in range(20):
                auto_index.request_resource(Path('/a'), ('query', i), factory)
            self.assertEqual(len(auto_index._read_request.get().resources), 8)
        context()
        self.assertIsNone(auto_index._read_request.get())


if __name__ == '__main__':
    unittest.main()
