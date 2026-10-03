import io
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import yaml

from tools.project_memory.config import load_config
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.hashing import sha256_text
from tools.project_memory.ignore import iter_indexable_files
from tools.project_memory.mcp import _tool_code, serve_stdio
from tools.project_memory.services.auto_index import auto_index_enabled, index_freshness
from tools.project_memory.services.code_provider import (code_query, provider_status, resolve_code_reference,
                                                       validate_code_reference, _run)
from tools.project_memory.services.code_migration import migrate_code
from tools.project_memory.services.context_builder import build_context
from tools.project_memory.services.index_project import index_project
from tools.project_memory.services import knowledge, rationale
from tools.project_memory.services.memory_relations import load_links, relation_details
from tools.project_memory.services.search import search
from tools.project_memory.vector.qdrant_store import QdrantLocalStore


class CodeProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'code'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / 'app.py').write_text('def run():\n    return "codemarker"\n')
        (self.repo / 'package.json').write_text('{"name":"fixture"}')
        (self.repo / 'README.md').write_text('materialmarker decisions\n')
        subprocess.run(['git', '-C', str(self.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Fixture', '-c',
                        'user.email=fixture@example.org', 'commit', '-qm', 'fixture'], check=True)
        self.revision = subprocess.run(['git', '-C', str(self.repo), 'rev-parse', 'HEAD'],
                                       capture_output=True, text=True, check=True).stdout.strip()
        self.registry = self.root / '.project-memory/registry.json'
        self.storage = self.repo / '.gitnexus'
        self.storage.mkdir()
        self.config = {'vector': {'backend': 'fallback'}, 'code_provider': {'backend': 'gitnexus',
            'command': ['/usr/bin/true'], 'registry_path': str(self.registry),
            'repositories': [{'id': 'fixture', 'name': 'fixture', 'path': 'code'}]}}
        (self.root / '.project-memory').mkdir()
        self.write_config()
        self.snapshot()

    def write_config(self):
        (self.root / '.project-memory/config.yaml').write_text(yaml.safe_dump(self.config))

    def snapshot(self):
        stamp = datetime.now(timezone.utc).isoformat()
        meta = {'repoPath': str(self.repo), 'storagePath': str(self.storage), 'indexedAt': stamp,
                'lastCommit': self.revision, 'runnerIdentity': {'cliVersion': '1.6.12'}}
        (self.storage / 'meta.json').write_text(json.dumps(meta))
        self.registry.write_text(json.dumps([{'name': 'fixture', 'path': str(self.repo),
            'storagePath': str(self.storage), 'indexedAt': stamp, 'lastCommit': self.revision}]))

    def test_exact_boundary_registry_and_read_no_scan(self):
        with patch('tools.project_memory.ignore.iter_project_files', side_effect=AssertionError('full source scan')):
            self.assertEqual(provider_status(self.root, 'fixture')['status'], 'current')
        self.assertEqual(code_query(self.root, repository_id='neighbour')['status'], 'unavailable')
        registry = json.loads(self.registry.read_text())
        registry[0]['path'] = str(self.root)
        self.registry.write_text(json.dumps(registry))
        with patch('tools.project_memory.services.code_provider._run', side_effect=AssertionError('unsafe external read')):
            self.assertEqual(code_query(self.root, 'search', repository_id='fixture', query='run')['status'], 'unavailable')

    def test_external_storage_requires_explicit_root(self):
        external = self.root / 'external-storage'
        self.storage.rename(external)
        self.storage = external
        self.snapshot()
        self.assertEqual(provider_status(self.root)['status'], 'unavailable')
        self.config['code_provider']['storage_root'] = str(external.parent)
        self.write_config()
        self.assertEqual(provider_status(self.root)['status'], 'current')

    def test_dirty_rename_and_snapshot_revision_status(self):
        (self.repo / 'app.py').write_text('def rename():\n    return 2\n')
        self.assertEqual(provider_status(self.root)['status'], 'stale')
        self.snapshot()
        self.assertEqual(provider_status(self.root)['status'], 'current')
        (self.repo / 'app.py').unlink()
        self.assertEqual(provider_status(self.root)['status'], 'stale')
        ref = dict(schema_version=1, provider='gitnexus', repository_id='fixture',
                   path='app.py', revision=self.revision)
        self.assertEqual(resolve_code_reference(self.root, ref)['reference_status'], 'missing')
        for field, value in [('path', '../escape.py'), ('repository_id', 'other'), ('revision', 'HEAD')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_code_reference(self.root, {**ref, field: value})

    def test_timeout_and_bounded_parameters(self):
        with patch('tools.project_memory.services.code_provider._run', side_effect=subprocess.TimeoutExpired('gitnexus', 1)):
            self.assertEqual(code_query(self.root, 'search', query='run')['status'], 'timeout')
        for kwargs in ({'limit': 100}, {'query': '--repo=other'}, {'path': '../escape'}, {'base': '--all'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                code_query(self.root, 'context', **{'query': 'run', **kwargs})
        with self.assertRaises(ValueError):
            _tool_code(self.root, {'root': '/other'})

    def test_cli_log_stream_and_absolute_repository_routing(self):
        calls = []
        class Process:
            returncode = 0
            def __init__(self, argv, **kwargs):
                calls.append((argv, kwargs))
                kwargs['stdout'].write(b'GitNexus Query (1.6.12)\n{"level":"info","msg":"loading"}\n{"level":"info","msg":"loaded"}\n{"definitions":[],"processes":[]}\n')
            def poll(self):
                return 0
        with patch('tools.project_memory.services.code_provider.subprocess.Popen', Process):
            evidence = _run(self.config['code_provider'], {'root': self.repo}, ['query', '--query', 'run'])
        self.assertEqual(evidence, {'definitions': [], 'processes': []})
        self.assertEqual(calls[0][0][-2:], ['--repo', str(self.repo)])
        self.assertFalse(calls[0][1]['shell'])

    def test_real_qdrant_retirement_preserves_durable_and_material_points(self):
        try:
            from qdrant_client.models import Distance, PointStruct, VectorParams
        except ImportError:
            self.skipTest('Optional Qdrant SDK is not installed in this interpreter')
        import uuid
        def point_id(value):
            return str(uuid.uuid5(uuid.NAMESPACE_URL, value))
        with patch('tools.project_memory.vector.qdrant_store.FastEmbedEmbeddings', side_effect=AssertionError('migration loads model')):
            vectors = QdrantLocalStore(self.root / '.project-memory/real-qdrant', backend='qdrant',
                                       root=self.root, load_embeddings=False)
        self.addCleanup(vectors.close)
        client = vectors.client
        client.create_collection(vectors.collection, vectors_config=VectorParams(size=2, distance=Distance.COSINE))
        payloads = {
            'native': {'file_path': 'code/app.py', 'kind': 'symbol'},
            'historic': {'file_path': 'code/app.py', 'kind': 'file'},
            'authored': {'file_path': 'code/app.py', 'kind': 'knowledge'},
            'material': {'file_path': 'notes.md', 'kind': 'file'},
        }
        client.upsert(vectors.collection, points=[PointStruct(id=point_id(key), vector=[1.0, 0.0], payload=value)
                                                 for key, value in payloads.items()], wait=True)
        vectors.retire_chunks({'native'}, code_paths={'code/app.py'})
        remaining = client.retrieve(vectors.collection, ids=[point_id(key) for key in payloads])
        self.assertEqual({row.id for row in remaining}, {point_id('authored'), point_id('material')})

    def test_non_git_snapshot_and_multi_repo_selection(self):
        import shutil
        shutil.rmtree(self.repo / '.git')
        self.revision = None
        self.snapshot()
        status = provider_status(self.root)
        self.assertEqual(status['status'], 'unknown')
        self.assertTrue(status['revision'].startswith('snapshot:'))
        self.config['code_provider']['repositories'].append({'id': 'second', 'path': '.', 'name': 'second'})
        self.write_config()
        self.assertEqual(provider_status(self.root)['status'], 'unavailable')
        self.assertEqual(provider_status(self.root, 'fixture')['status'], 'unknown')

    def test_slim_index_search_freshness_never_parses_code(self):
        (self.storage / 'dump.json').write_text('{"graph":"must-not-index"}')
        with patch('tools.project_memory.services.index_project._parser_for', return_value=(None, None, 'text')) as parser:
            index_project(self.root, 'full')
            self.assertEqual(parser.call_args_list, [])
        store = SQLiteGraphStore(self.root, self.root / '.project-memory/graph.sqlite')
        self.assertEqual(store.indexed_file_paths(), {'code/README.md'})
        self.assertFalse(auto_index_enabled(self.root, 'search'))
        (self.repo / 'app.py').write_text('def changed(): return 3\n')
        self.assertTrue(index_freshness(self.root).fresh)
        self.assertTrue(search(self.root, 'materialmarker'))
        self.assertEqual(search(self.root, 'codemarker'), [])

    def test_unassigned_and_unsupported_sources_remain_text_only(self):
        (self.root / 'analytics.py').write_text('unassignedmarker scientific analysis\n')
        (self.repo / 'index.html').write_text('<script>unsupportedmarker()</script>')
        self.config['code_provider']['document_extensions'] = ['.html']
        self.config['indexing'] = {'include_extensions': ['.py', '.html', '.md', '.json']}
        self.write_config()
        with patch('tools.project_memory.services.index_project._parser_for', side_effect=AssertionError('native code parser')):
            index_project(self.root, 'full')
        self.assertTrue(search(self.root, 'unassignedmarker'))
        self.assertTrue(search(self.root, 'unsupportedmarker'))
        store = SQLiteGraphStore(self.root, self.root / '.project-memory/graph.sqlite')
        self.assertEqual(store.query("SELECT id FROM nodes WHERE kind='Symbol'"), [])

    def test_memory_only_context_makes_no_provider_calls(self):
        with patch('tools.project_memory.services.code_provider.code_query', side_effect=AssertionError('unrequested code query')):
            context = build_context(self.root, 'planning')
        self.assertIn('fixture', context)

    def test_context_provider_offline_preserves_memory(self):
        (self.root / 'source.md').write_text('memorystablemarker known decision\n')
        entry = knowledge.add_knowledge(self.root, 'decision', 'Decision', 'source.md')
        self.registry.unlink()
        with patch('tools.project_memory.services.index_project.index_project', side_effect=AssertionError('read indexing')):
            context = build_context(self.root, 'memorystablemarker', include_code=True)
        self.assertIn(entry.id, context)
        self.assertIn('unavailable', context)

    def test_versioned_code_link_roundtrip_and_resolution(self):
        (self.root / 'source.md').write_text('Evidence\n')
        reference = dict(schema_version=1, provider='gitnexus', repository_id='fixture', path='app.py', revision=self.revision)
        link = dict(relation='supports', target={'kind': 'code', 'id': 'run', 'reference': reference},
                    source={'path': 'source.md', 'revision': sha256_text('Evidence\n')},
                    evidence=['source.md'], confidence=0.8, status='current')
        record = rationale.add_rationale(self.root, 'decision', 'Reason', 'source.md', links=[link])
        store = rationale._store(self.root)
        self.assertEqual(load_links(store, 'rationale', record.id), [link])
        self.assertEqual(relation_details(store, 'rationale', record.id)[0]['target_status'], 'current')
        (self.repo / 'app.py').write_text('changed\n')
        self.assertEqual(relation_details(store, 'rationale', record.id)[0]['target_status'], 'stale')

    def test_bound_mcp_rejects_other_root(self):
        with patch.dict(os.environ, {'PMEM_BOUND_ROOT': str(self.root)}), self.assertRaises(ValueError):
            serve_stdio(self.repo, io.StringIO(''), io.StringIO())

    def test_symbol_reference_requires_exact_found_locator(self):
        ref = dict(schema_version=1, provider='gitnexus', repository_id='fixture', path='app.py',
                   revision=self.revision, symbol='run')
        for evidence in ({}, [], {'status': 'found', 'symbol': {'name': 'other', 'filePath': 'app.py'}}):
            with self.subTest(evidence=evidence), patch('tools.project_memory.services.code_provider._run', return_value=evidence):
                self.assertEqual(resolve_code_reference(self.root, ref)['reference_status'], 'unresolved')
        with patch('tools.project_memory.services.code_provider._run', return_value={'status': 'found', 'symbol': {'name': 'run', 'filePath': 'app.py'}}):
            self.assertEqual(resolve_code_reference(self.root, ref)['reference_status'], 'current')
        with patch('tools.project_memory.services.code_provider._run', return_value={'error': "Symbol 'run' not found"}):
            self.assertEqual(resolve_code_reference(self.root, ref)['reference_status'], 'missing')


class CodeMigrationTests(CodeProviderTests):
    def prepare_native_index(self):
        self.config['code_provider']['backend'] = 'native'
        self.write_config()
        index_project(self.root, 'full')
        self.config['code_provider']['backend'] = 'gitnexus'
        self.write_config()

    def test_vector_failure_rolls_back_database_and_exact_vector_bytes(self):
        self.prepare_native_index()
        fallback = self.root / '.project-memory/qdrant/fallback_chunks.jsonl'
        before = fallback.read_bytes()
        original = QdrantLocalStore.retire_chunks
        def fail_after_retire(store, ids, **kwargs):
            original(store, ids, **kwargs)
            raise RuntimeError('fixture vector failure')
        with patch.object(QdrantLocalStore, 'retire_chunks', fail_after_retire), self.assertRaisesRegex(RuntimeError, 'rolled back including vectors'):
            migrate_code(self.root, apply=True)
        self.assertEqual(fallback.read_bytes(), before)
        self.assertTrue(SQLiteGraphStore(self.root, self.root / '.project-memory/graph.sqlite').query("SELECT id FROM nodes WHERE kind='Symbol'"))

    def test_internal_vector_symlink_refused_before_backup(self):
        self.prepare_native_index()
        with tempfile.TemporaryDirectory() as outside:
            (self.root / '.project-memory/qdrant/foreign').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'contains symlinks'):
                migrate_code(self.root, apply=True)
        self.assertFalse((self.root / '.project-memory/backups').exists())

    def test_sqlite_commit_failure_restores_vectors_and_code_rows(self):
        from tools.project_memory.graph.sqlite_store import ManagedConnection
        self.prepare_native_index()
        fallback = self.root / '.project-memory/qdrant/fallback_chunks.jsonl'
        before = fallback.read_bytes()
        commits = []
        def fail_second_commit(connection):
            commits.append(connection.in_transaction)
            if len(commits) == 2:
                raise sqlite3.OperationalError('fixture commit failure')
            sqlite3.Connection.commit(connection)
        with patch.object(ManagedConnection, 'commit', fail_second_commit), self.assertRaisesRegex(RuntimeError, 'rolled back including vectors'):
            migrate_code(self.root, apply=True)
        self.assertEqual(fallback.read_bytes(), before)
        self.assertTrue(SQLiteGraphStore(self.root, self.root / '.project-memory/graph.sqlite').query("SELECT id FROM nodes WHERE kind='Symbol'"))

    def test_historical_owned_code_vectors_retired_but_durable_kind_kept(self):
        self.prepare_native_index()
        path = self.root / '.project-memory/qdrant'
        vectors = QdrantLocalStore(path, backend='fallback', root=self.root)
        vectors.upsert_chunk('historical-code-range', 'past source', {'file_path': 'code/app.py', 'kind': 'symbol'})
        vectors.upsert_chunk('same-path-durable', 'authored memory', {'file_path': 'code/app.py', 'kind': 'knowledge'})
        vectors.close()
        migrate_code(self.root, apply=True)
        rows = [json.loads(line) for line in (path / 'fallback_chunks.jsonl').read_text().splitlines()]
        self.assertFalse(any(row['id'] == 'historical-code-range' for row in rows))
        self.assertTrue(any(row['id'] == 'same-path-durable' for row in rows))

    def test_empty_repositories_memory_only_context_remains_available(self):
        self.config['code_provider']['repositories'] = []
        self.write_config()
        (self.root / 'source.md').write_text('emptyrepomemorymarker decision\n')
        record = knowledge.add_knowledge(self.root, 'decision', 'Decision', 'source.md')
        with patch('tools.project_memory.services.code_provider.code_query', side_effect=AssertionError('emptyrepo graph call')):
            self.assertIn(record.id, build_context(self.root, 'emptyrepomemorymarker'))

    def test_preview_apply_backup_restore_durable_history_vectors(self):
        self.config['code_provider']['backend'] = 'native'
        self.write_config()
        index_project(self.root, 'full')
        (self.root / 'source.md').write_text('durablemarker decision\n')
        k = knowledge.add_knowledge(self.root, 'decision', 'Decision', 'source.md', links=['git:fixture'])
        knowledge.update_knowledge(self.root, k.id, 'source.md')
        r = rationale.add_rationale(self.root, 'decision', 'Reason', 'source.md', links=['knowledge:' + k.id])
        rationale.retire_rationale(self.root, r.id)
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in (self.root / '.project-memory/knowledge').rglob('*.md')}
        before.update({p.relative_to(self.root).as_posix(): p.read_bytes() for p in (self.root / '.project-memory/rationale').rglob('*.md')})
        self.config['code_provider']['backend'] = 'gitnexus'
        self.write_config()
        preview = migrate_code(self.root)
        self.assertIn('code/app.py', preview['code_paths'])
        self.assertIn('code/package.json', preview['code_paths'])
        self.assertNotIn('code/README.md', preview['code_paths'])
        result = migrate_code(self.root, apply=True)
        self.assertEqual(result['durable_digest'], result['durable_digest_after'])
        self.assertGreater(result['vector_status']['removed_fallback_vectors'], 0)
        for path, body in before.items():
            self.assertEqual((self.root / path).read_bytes(), body)
        store = SQLiteGraphStore(self.root, self.root / '.project-memory/graph.sqlite')
        self.assertEqual(store.query('PRAGMA foreign_key_check'), [])
        self.assertFalse(store.query("SELECT id FROM nodes WHERE kind='Symbol'"))
        self.assertTrue(search(self.root, 'durablemarker'))
        self.assertTrue(search(self.root, 'materialmarker'))
        payloads = [json.loads(line)['payload'] for line in (self.root / '.project-memory/qdrant/fallback_chunks.jsonl').read_text().splitlines()]
        self.assertFalse(any(item.get('file_path') == 'code/app.py' for item in payloads))
        self.assertTrue(any(item.get('file_path') == k.path for item in payloads))
        repeat = migrate_code(self.root, apply=True)
        self.assertIsNone(repeat['backup'])
        with closing(sqlite3.connect(result['backup'])) as backup, tempfile.TemporaryDirectory() as recovered:
            with closing(sqlite3.connect(Path(recovered) / 'restored.sqlite')) as restored:
                backup.backup(restored)
                self.assertGreater(restored.execute("SELECT count(*) FROM nodes WHERE kind='Symbol'").fetchone()[0], 0)
                self.assertEqual(restored.execute('SELECT version FROM knowledge_entries WHERE id=?', (k.id,)).fetchone()[0], 2)


if __name__ == '__main__':
    unittest.main()
