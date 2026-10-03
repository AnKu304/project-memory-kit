from pathlib import Path
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from tools.project_memory.hashing import sha256_text
from tools.project_memory.services import knowledge, rationale
from tools.project_memory.services.human import export_human, search_human, sync_human
from tools.project_memory.services.index_project import index_project
from tools.project_memory.services.search import search


class RetiredMemorySafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        config = self.root / '.project-memory/config.yaml'
        config.parent.mkdir()
        config.write_text('vector:\n  backend: fallback\nindexing:\n  auto_index:\n    enabled: false\nmodules:\n  human:\n    enabled: true\n')
        self.source = self.root / 'note.md'
        self.source.write_text('# Record\n\nobsoletepolicymarker decision evidence.\n')

    def add(self, kind, title='Old policy', **kwargs):
        module = knowledge if kind == 'knowledge' else rationale
        return getattr(module, 'add_' + kind)(self.root, 'decision', title, 'note.md', **kwargs)

    def test_retire_updates_show_and_hash_without_changing_body_or_links(self):
        for kind in ('knowledge', 'rationale'):
            with self.subTest(kind=kind):
                module = knowledge if kind == 'knowledge' else rationale
                result = self.add(kind, links=['git:fixture'])
                before = (self.root / result.path).read_text()
                getattr(module, 'retire_' + kind)(self.root, result.id)
                content = getattr(module, 'show_' + kind)(self.root, result.id)
                self.assertEqual(content, before.replace('status: current\n', 'status: archived\n', 1))
                row = module._store(self.root).query(f'SELECT status, content_hash, version FROM {kind}_entries WHERE id=?', (result.id,))[0]
                self.assertEqual((row['status'], row['content_hash'], row['version']), ('archived', sha256_text(content), 1))

    def test_retired_human_copy_is_hidden_before_and_after_source_refresh(self):
        for kind in ('knowledge', 'rationale'):
            with self.subTest(kind=kind):
                module = knowledge if kind == 'knowledge' else rationale
                result = self.add(kind, title=kind)
                export_human(self.root)
                self.assertTrue(search_human(self.root, 'obsoletepolicymarker'))
                getattr(module, 'retire_' + kind)(self.root, result.id)
                self.assertEqual(search(self.root, 'obsoletepolicymarker', audience='all'), [])
                self.assertEqual(search_human(self.root, 'obsoletepolicymarker'), [])
                self.source.write_text('unrelated source refresh\n')
                index_project(self.root, 'changed')
                self.assertEqual(search(self.root, 'obsoletepolicymarker', audience='all'), [])
                self.assertEqual(module._store(self.root).query(f'SELECT status FROM {kind}_entries WHERE id=?', (result.id,))[0]['status'], 'archived')
                self.assertTrue(sync_human(self.root).conflicts)
                self.source.write_text('# Record\n\nobsoletepolicymarker decision evidence.\n')

    def test_retire_needs_no_vector_backend_and_keeps_current_product_facts(self):
        for index in range(12):
            result = self.add('knowledge', title=f'Archived {index}')
            with patch.object(knowledge, '_vectors', side_effect=AssertionError('retire opened vectors')):
                knowledge.retire_knowledge(self.root, result.id)
        self.source.write_text('# Product skills\n\nobsoletepolicymarker defines product skills.\n')
        current = self.add('knowledge', title='Product skills')
        rows = search(self.root, 'obsoletepolicymarker', limit=1)
        self.assertEqual([row['path'] for row in rows], [current.path])

    def test_semantic_hits_follow_database_lifecycle_even_with_stale_payload(self):
        old = self.add('knowledge')
        export_human(self.root)
        knowledge.retire_knowledge(self.root, old.id)
        self.source.write_text('# Product skills\n\ncurrent product decision.\n')
        current = self.add('knowledge', title='Product skills')
        store = knowledge._store(self.root)
        hits = [{'chunk_id': row['chunk_id'], 'score': 1.0 if row['path'] != current.path else 0.8,
                 'payload': {'status': 'current'}}
                for row in store.query('SELECT chunk_id, path FROM chunks_fts')]
        hits.sort(key=lambda hit: hit['score'], reverse=True)

        class StaleVectors:
            @contextmanager
            def query_session(self):
                yield self

            def search(self, query, limit, *, query_filter):
                return hits[:limit]

            def close(self):
                pass

        from tools.project_memory.config import load_config
        cfg = {**load_config(self.root), 'vector': {'backend': 'auto'}}
        with patch('tools.project_memory.services.search.load_config', return_value=cfg), \
                patch('tools.project_memory.services.search.QdrantLocalStore', return_value=StaleVectors()):
            rows = search(self.root, 'semantic-only-query', limit=1)
        self.assertEqual([row['path'] for row in rows], [current.path])
        self.assertIn('vector', rows[0]['reason'])

    def test_retirement_keeps_show_history_but_no_direct_chunks_for_legacy_readers(self):
        for kind in ('knowledge', 'rationale'):
            with self.subTest(kind=kind):
                module = knowledge if kind == 'knowledge' else rationale
                old = self.add(kind)
                self.source.write_text('# Replacement\n\nnewpolicymarker approved decision.\n')
                self.add(kind, title='New policy', supersedes=old.id)
                content = getattr(module, 'show_' + kind)(self.root, old.id)
                self.assertIn('status: superseded\n', content)
                self.assertIn('obsoletepolicymarker', content)
                self.assertEqual(module._store(self.root).query('SELECT chunk_id FROM chunks_fts WHERE path=?', (old.path,)), [])
                getattr(module, 'retire_' + kind)(self.root, old.id)
                self.assertIn('status: archived\n', getattr(module, 'show_' + kind)(self.root, old.id))
                self.assertEqual(module._store(self.root).query('SELECT chunk_id FROM chunks_fts WHERE path=?', (old.path,)), [])
                rows = getattr(module, 'search_' + kind)(self.root, 'obsoletepolicymarker')
                self.assertEqual(rows, [])
                rows = getattr(module, 'search_' + kind)(self.root, 'newpolicymarker')
                self.assertTrue(rows)
                self.assertTrue(all(row['status'] == 'current' for row in rows))
                self.source.write_text('# Record\n\nobsoletepolicymarker decision evidence.\n')


if __name__ == '__main__':
    unittest.main()
