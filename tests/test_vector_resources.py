from __future__ import annotations

from contextlib import nullcontext
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from tools.project_memory.vector.qdrant_store import QdrantLocalStore


class VectorResourceTests(unittest.TestCase):
    def test_failed_embedding_initialization_closes_client_before_unlock(self):
        for backend in ('auto', 'qdrant'):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as directory:
                events = []
                client = Mock()
                client.close.side_effect = lambda: events.append('close')
                lock = Mock()
                lock.__enter__ = Mock()
                lock.__exit__ = Mock(side_effect=lambda *_: events.append('unlock'))
                module = types.SimpleNamespace(QdrantClient=Mock(return_value=client))
                with patch.dict(sys.modules, {'qdrant_client': module}), patch(
                    'tools.project_memory.vector.qdrant_store.MemoryResourceLock', return_value=lock
                ), patch('tools.project_memory.vector.qdrant_store.FastEmbedEmbeddings', side_effect=ValueError('fixture')):
                    expected = self.assertRaises(RuntimeError) if backend == 'qdrant' else nullcontext()
                    with expected:
                        store = QdrantLocalStore(Path(directory), backend=backend)
                        self.assertEqual(store.backend, 'fallback')
                        store.close()
                    self.assertEqual(events, ['close', 'unlock'])

    def test_batch_matches_immediate_jsonl_and_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            direct = QdrantLocalStore(root / 'direct', backend='fallback')
            batched = QdrantLocalStore(root / 'batch', backend='fallback')
            for store in (direct, batched):
                store.upsert_chunk('seed', 'seed text', {'kind': 'knowledge'})
            operations = [('a', 'first'), ('b', 'second'), ('a', 'updated'), ('c', 'third'), ('seed', 'new seed')]
            for chunk_id, text in operations:
                direct.upsert_chunk(chunk_id, text, {'text': text})
            with batched.batch_fallback(max_chunks=2):
                for chunk_id, text in operations:
                    batched.upsert_chunk(chunk_id, text, {'text': text})
                    self.assertLess(len(batched._fallback_pending), 2)
            self.assertEqual(direct.fallback_file.read_bytes(), batched.fallback_file.read_bytes())
            self.assertEqual(batched.search('updated'), [])

    def test_batch_flushes_successful_rows_when_body_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            store = QdrantLocalStore(Path(directory), backend='fallback')
            with self.assertRaisesRegex(ValueError, 'later operation'):
                with store.batch_fallback():
                    store.upsert_chunk('saved', 'first success', {})
                    raise ValueError('later operation')
            rows = [json.loads(line) for line in store.fallback_file.read_text().splitlines()]
            self.assertEqual([row['id'] for row in rows], ['saved'])

    def test_failed_replace_preserves_existing_file_and_removes_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            store = QdrantLocalStore(Path(directory), backend='fallback')
            store.upsert_chunk('original', 'original', {})
            original = store.fallback_file.read_bytes()
            with patch('os.replace', side_effect=OSError('fixture disk failure')):
                with self.assertRaises(OSError):
                    store.upsert_chunk('new', 'new', {})
            self.assertEqual(store.fallback_file.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [store.fallback_file])

    def test_pending_payload_is_a_snapshot_and_oversized_row_flushes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = QdrantLocalStore(Path(directory), backend='fallback')
            payload = {'source': 'original'}
            with store.batch_fallback():
                store.upsert_chunk('small', 'small', payload)
                payload['source'] = 'mutated'
                store.upsert_chunk('large', 'large', {'source': 'x' * (1024 * 1024)})
                self.assertEqual(store._fallback_pending_bytes, 0)
                self.assertFalse(store._fallback_pending)
            rows = [json.loads(line) for line in store.fallback_file.read_text().splitlines()]
            self.assertEqual(rows[0]['payload']['source'], 'original')
            self.assertEqual([row['id'] for row in rows], ['small', 'large'])

    def test_malformed_existing_jsonl_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            store = QdrantLocalStore(Path(directory), backend='fallback')
            original = b'{"id":"old","vector":[],"payload":{}}\nnot-json\n'
            store.fallback_file.write_bytes(original)
            with self.assertRaises(json.JSONDecodeError):
                store.upsert_chunk('new', 'new', {})
            self.assertEqual(store.fallback_file.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [store.fallback_file])

    def test_index_batches_fallback_and_noop_preserves_file(self):
        from tools.project_memory.services.index_project import index_project
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'app.py').write_text('\n'.join(f'def example_{i}():\n    return {i}\n' for i in range(130)))
            instances = []
            def factory(*args, **kwargs):
                kwargs['backend'] = 'fallback'
                store = QdrantLocalStore(*args, **kwargs)
                store._flush_fallback = Mock(wraps=store._flush_fallback)
                instances.append(store)
                return store
            with patch('tools.project_memory.services.index_project.QdrantLocalStore', side_effect=factory):
                summary = index_project(root, mode='full')
                self.assertIn('indexed=1', summary)
                store = instances[0]
                self.assertEqual(store._flush_fallback.call_count, 2)
                original = store.fallback_file.read_bytes()
                self.assertEqual(len(original.splitlines()), 130)
                summary = index_project(root, mode='changed')
                self.assertIn('skipped=1', summary)
                self.assertEqual(store.fallback_file.read_bytes(), original)

    def test_index_retries_files_after_final_fallback_replace_failure(self):
        from tools.project_memory.services.index_project import index_project
        from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('alpha', 'beta'):
                (root / f'{name}.py').write_text(f'def {name}():\n    return 1\n')
            def factory(*args, **kwargs):
                kwargs['backend'] = 'fallback'
                return QdrantLocalStore(*args, **kwargs)
            with patch('tools.project_memory.services.index_project.QdrantLocalStore', side_effect=factory):
                with patch('os.replace', side_effect=OSError('fixture disk failure')):
                    with self.assertRaises(OSError):
                        index_project(root, mode='full')
                graph = SQLiteGraphStore(root, root / '.project-memory/graph.sqlite')
                self.assertIsNone(graph.file_hash('alpha.py'))
                self.assertIsNone(graph.file_hash('beta.py'))
                self.assertTrue(graph.query("SELECT id FROM nodes WHERE kind='Symbol'"))
                summary = index_project(root, mode='changed')
                self.assertIn('indexed=2', summary)
                rows = (root / '.project-memory/qdrant/fallback_chunks.jsonl').read_text().splitlines()
                self.assertEqual(len(rows), 2)

    def test_file_hash_is_published_only_after_vectors_are_persisted(self):
        from tools.project_memory.services.index_project import index_project
        from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'app.py').write_text('def alpha():\n    return 1\n\ndef beta():\n    return 2\n')
            original = SQLiteGraphStore.update_file_state
            published = []
            original_replace = os.replace
            def replace(source, destination):
                graph = SQLiteGraphStore(root, root / '.project-memory/graph.sqlite')
                self.assertIsNone(graph.file_hash('app.py'), 'hash exists before replace')
                return original_replace(source, destination)
            def publish(graph, path, file_hash, parser, warnings):
                vector_file = root / '.project-memory/qdrant/fallback_chunks.jsonl'
                self.assertTrue(vector_file.exists(), 'hash published before vector flush')
                self.assertEqual(len(vector_file.read_text().splitlines()), 2)
                published.append(path)
                return original(graph, path, file_hash, parser, warnings)
            def factory(*args, **kwargs):
                kwargs['backend'] = 'fallback'
                return QdrantLocalStore(*args, **kwargs)
            with patch('tools.project_memory.services.index_project.QdrantLocalStore', side_effect=factory), patch.object(
                SQLiteGraphStore, 'update_file_state', publish
            ), patch('os.replace', side_effect=replace):
                index_project(root, mode='full')
            self.assertEqual(published, ['app.py'])

    def test_qdrant_search_remains_available_with_fake_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Mock()
            client.collection_exists.return_value = True
            client.query_points.return_value = types.SimpleNamespace(points=[
                types.SimpleNamespace(payload={'chunk_id': 'semantic-hit'}, score=0.9)
            ])
            module = types.SimpleNamespace(QdrantClient=Mock(return_value=client))
            embeddings = Mock()
            embeddings.embed.return_value = [0.1, 0.2]
            with patch.dict(sys.modules, {'qdrant_client': module}), patch(
                'tools.project_memory.vector.qdrant_store.FastEmbedEmbeddings', return_value=embeddings
            ):
                store = QdrantLocalStore(Path(directory), backend='qdrant', url='http://fixture.invalid')
                with store.batch_fallback():
                    self.assertEqual(store.search('meaning')[0]['chunk_id'], 'semantic-hit')
                self.assertFalse(store.fallback_file.exists())
                store.close()
                client.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
