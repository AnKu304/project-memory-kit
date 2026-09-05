from contextlib import contextmanager, redirect_stdout
import argparse
import io
from pathlib import Path
import tempfile
import sys
import types
import unittest
from unittest.mock import patch, Mock

from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.services.search import search
from tools.project_memory.services.memory_scope import classify_memory_path


class SearchFilterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = SQLiteGraphStore(self.root, self.root / '.project-memory/graph.sqlite')
        self.store.initialize()
        self.cfg = {'vector': {'backend': 'fallback'}, 'memory': {'classification': {
            'domains': ['custom'], 'rules': [{'pattern': 'special/*', 'domain': 'custom'}]}}}
        self.addCleanup(patch.stopall)
        self.freshness = patch('tools.project_memory.services.search.ensure_fresh_index').start()
        patch('tools.project_memory.services.search.load_config', return_value=self.cfg).start()
        for i in range(40):
            self.store.upsert_chunk(f'.agents/skills/skill{i}.md', 'session', 1, 1, 'session')
        for path in ('frontend/view.ts', 'backend/server.py', 'research/study.md', 'special/note.md'):
            self.store.upsert_chunk(path, path, 1, 1, f'session project implementation detail {path}')

    def test_legacy_tooling_does_not_consume_project_top_k(self):
        rows = search(self.root, 'session', limit=2)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row['memory_audience'] == 'project' for row in rows))
        self.assertFalse(any(row['path'].startswith('.agents') for row in rows))
        self.assertTrue(all(row['memory_scope'] == 'project' for row in rows))

    def test_audience_and_domains_and_type(self):
        self.assertTrue(all(row['memory_audience'] == 'agent_tooling' for row in search(self.root, 'session', limit=3, audience='agent_tooling')))
        self.assertTrue(any(row['path'].startswith('.agents') for row in search(self.root, 'session', audience='all')))
        for domain, path in [('frontend', 'frontend/view.ts'), ('backend', 'backend/server.py'), ('research', 'research/study.md'), ('custom', 'special/note.md')]:
            rows = search(self.root, 'session', domain=domain)
            self.assertEqual([row['path'] for row in rows], [path])
        self.assertEqual(search(self.root, 'session', domain='frontend', memory_type='knowledge'), [])

    def test_outside_paths_are_excluded_even_for_all_audiences(self):
        self.store.upsert_chunk('../outside.py', 'outside', 1, 1, 'session')
        self.store.upsert_chunk('/outside.py', 'outside', 1, 1, 'session')
        rows = search(self.root, 'session', audience='all', limit=100)
        self.assertFalse(any('outside' in row['path'] for row in rows))

    def test_invalid_filters_fail_before_auto_index(self):
        for filters in ({'audience': 'shared'}, {'domain': 'unknown'}, {'memory_type': 'invalid'}):
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                search(self.root, 'session', **filters)
        self.freshness.assert_not_called()

    def test_layer_is_still_independent(self):
        cid = self.store.upsert_chunk('.project-memory/knowledge/research.md', 'note', 1, 1, 'session')
        with self.store.connect() as conn:
            conn.execute("UPDATE nodes SET layer='knowledge' WHERE id=?", (cid,))
        rows = search(self.root, 'session', layer='knowledge', memory_type='knowledge')
        self.assertEqual([row['chunk_id'] for row in rows], [cid])

    def fake_vectors(self, legacy=False, overflow=False):
        hits = []
        for row in self.store.query('SELECT chunk_id, path FROM chunks_fts ORDER BY path'):
            metadata = {} if legacy else classify_memory_path(self.root, row['path'], self.cfg)
            hits.append({'chunk_id': row['chunk_id'], 'score': 1.0 if row['path'].startswith('.agents') else 0.8,
                         'payload': metadata})
        if overflow:
            hits = [{'chunk_id': f'foreign-{i}', 'score': 1.0, 'payload': {}} for i in range(1100)] + hits
        if not legacy:
            for row in self.store.query('SELECT DISTINCT path FROM chunks_fts'):
                self.store.upsert_node(kind='File', name=Path(row['path']).name, path=row['path'],
                                       properties=classify_memory_path(self.root, row['path'], self.cfg))
        calls = []
        class Vectors:
            @contextmanager
            def query_session(self):
                yield self
            def search(self, query, limit, *, query_filter):
                calls.append((limit, query_filter))
                if query_filter is None:
                    selected = hits
                elif 'must' in query_filter:
                    selected = [hit for hit in hits if all(hit['payload'].get(c['key']) == c['match']['value'] for c in query_filter['must'])]
                else:
                    selected = [hit for hit in hits if any(not hit['payload'].get(c['is_empty']['key']) for c in query_filter['should'])]
                return selected[:limit]
            def close(self):
                pass
        self.cfg['vector']['backend'] = 'auto'
        patch('tools.project_memory.services.search.QdrantLocalStore', return_value=Vectors()).start()
        return calls

    def test_modern_vector_filter_is_sent_before_candidate_limit(self):
        calls = self.fake_vectors()
        rows = search(self.root, 'session', limit=2, domain='backend')
        self.assertEqual([row['path'] for row in rows], ['backend/server.py'])
        must = calls[0][1]['must']
        self.assertIn({'key': 'memory_audience', 'match': {'value': 'project'}}, must)
        self.assertIn({'key': 'memory_domain', 'match': {'value': 'backend'}}, must)
        self.assertIn('vector', rows[0]['reason'])

    def test_legacy_vector_expands_past_tooling(self):
        for i in range(90):
            self.store.upsert_chunk(f'.agents/additional/{i}.md', 'session', 1, 1, 'session')
        calls = self.fake_vectors(legacy=True)
        rows = search(self.root, 'session', limit=2)
        self.assertEqual(len(rows), 2)
        self.assertTrue(any(limit > 64 for limit, _ in calls))
        self.assertTrue(all(row['memory_audience'] == 'project' for row in rows))

    def test_legacy_cap_is_explicit_even_when_no_lexical_results(self):
        self.fake_vectors(legacy=True, overflow=True)
        rows = search(self.root, 'no-matching-token', domain='design')
        self.assertEqual(rows, [])
        self.assertTrue(any('cap reached' in item for item in rows.diagnostics))

    def test_current_path_classification_overrides_wrong_vector_payload(self):
        calls = self.fake_vectors()
        self.cfg['memory']['classification']['rules'].insert(0, {'pattern': 'backend/*', 'audience': 'agent_tooling'})
        rows = search(self.root, 'session', domain='backend')
        self.assertEqual(rows, [])
        self.assertTrue(any('stale' in item for item in rows.diagnostics))

    def test_changed_domain_keeps_semantic_hit_despite_old_payload(self):
        self.fake_vectors()
        self.cfg['memory']['classification']['rules'].insert(0, {'pattern': 'frontend/*', 'domain': 'backend'})
        rows = search(self.root, 'no-lexical-match', domain='backend')
        self.assertIn('frontend/view.ts', [row['path'] for row in rows])
        self.assertTrue(any('stale' in item for item in rows.diagnostics))

    def test_vector_adapter_forwards_typed_filter_and_reuses_embedding(self):
        from tools.project_memory.vector.qdrant_store import QdrantLocalStore
        class Filter:
            def __init__(self, **values):
                self.values = values
        client = Mock()
        client.collection_exists.return_value = True
        client.query_points.return_value = types.SimpleNamespace(points=[])
        client.search.return_value = []
        embedder = Mock()
        embedder.embed.return_value = [0.1, 0.2]
        modules = {'qdrant_client': types.SimpleNamespace(QdrantClient=Mock(return_value=client)),
                   'qdrant_client.models': types.SimpleNamespace(Filter=Filter)}
        with patch.dict(sys.modules, modules), patch('tools.project_memory.vector.qdrant_store.FastEmbedEmbeddings', return_value=embedder):
            vectors = QdrantLocalStore(self.root / 'vectors', backend='qdrant', url='http://fixture.invalid')
            filters = {'must': [{'key': 'memory_scope', 'match': {'value': 'project'}}]}
            with vectors.query_session():
                vectors.search('session', 10, query_filter=filters)
                client.query_points.side_effect = AttributeError('old client')
                vectors.search('session', 20, query_filter=filters)
            embedder.embed.assert_called_once_with('session')
            self.assertEqual(client.search.call_args.kwargs['query_filter'].values, filters)
            self.assertEqual(client.query_points.call_args.kwargs['query_filter'].values, filters)
            self.assertIsNone(vectors._query_cache)
            vectors.close()

    def test_cli_mcp_filters_and_shared_rejection(self):
        from tools.project_memory.cli import command_search
        from tools.project_memory.mcp import _tool_search, _handle_tool_call
        from tools.project_memory.mcp_tools import TOOLS
        out = io.StringIO()
        args = argparse.Namespace(query='session', limit=2, layer=None, debug=False,
                                  audience='project', domain='backend', memory_type='code')
        with patch('tools.project_memory.cli.root', return_value=self.root), redirect_stdout(out):
            self.assertEqual(command_search(args), 0)
        self.assertIn('backend/server.py', out.getvalue())
        result = _tool_search(self.root, {'query': 'session', 'domain': 'research', 'type': 'document'})
        self.assertEqual(result['structuredContent']['results'][0]['memory_domain'], 'research')
        self.assertEqual(result['structuredContent']['filters']['scope'], 'project')
        error = _handle_tool_call(self.root, 1, {'name': 'pmem_search', 'arguments': {'query': 'session', 'scope': 'shared'}})
        self.assertTrue(error['result']['isError'])
        for tool in TOOLS:
            if tool['name'] in {'pmem_search', 'pmem_search_debug'}:
                self.assertIn('audience', tool['inputSchema']['properties'])


if __name__ == '__main__':
    unittest.main()
