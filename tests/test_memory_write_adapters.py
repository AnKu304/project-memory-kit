from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.project_memory import cli, mcp
from tools.project_memory.services import knowledge, rationale
from tools.project_memory.services.concurrency import MemoryWriteLock, queue_items, write_lock_path
from tools.project_memory.services.memory_relations import load_links
from tools.project_memory.hashing import sha256_text


class MemoryWriteAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'note.md').write_text('A local note')
        for module in (knowledge, rationale):
            def index(*args, **kwargs):
                self.assertTrue(write_lock_path(self.root).exists(), 'Write must hold lock')
            guard = patch.object(module, '_index_entry', side_effect=index)
            guard.start()
            self.addCleanup(guard.stop)

    def call(self, name, args):
        return mcp._handle_tool_call(self.root, 1, {'name': name, 'arguments': args})

    def test_mcp_add_update_structured_links_and_legacy_evidence(self):
        link = dict(relation='affects', target={'kind': 'file', 'id': 'note.md'},
                    source={'path': 'note.md', 'revision': sha256_text('A local note')},
                    evidence=['note.md'], confidence=0.6, status='current')
        for kind in ('knowledge', 'rationale'):
            args = {'type': 'decision', 'title': kind, 'file': 'note.md', 'links': ['git:abc', link]}
            if kind == 'rationale':
                args['evidence'] = ['git:abc']
            result = self.call('pmem_' + kind + '_add', args)['result']
            self.assertFalse(result['isError'], result)
            self.assertEqual(result['structuredContent']['status'], 'saved')
            self.assertTrue(result['structuredContent']['completed'])
            result = self.call('pmem_' + kind + '_update', {'id': kind, 'file': 'note.md'})['result']
            self.assertFalse(result['isError'], result)
            store = knowledge._store(self.root)
            self.assertEqual(load_links(store, kind, kind), ['git:abc', link])

    def test_unknown_or_malformed_input_fails_before_lock_or_db(self):
        cases = [{'type': 'decision', 'title': 'X', 'file': 'note.md', 'root': '/tmp'},
                 {'type': 'decision', 'title': 'X', 'file': 'note.md', 'links': [{}]},
                 {'type': 'decision', 'title': 'X', 'file': '../elsewhere.md'},
                 {'type': 'decision', 'title': 'X', 'file': 'note.md', 'links': '[]'}]
        for args in cases:
            response = self.call('pmem_knowledge_add', args)
            self.assertTrue(response['result']['isError'], response)
            self.assertFalse((self.root / '.project-memory').exists())

    def test_busy_queue_is_pending_and_replay_preserves_data(self):
        link = dict(relation='affects', target={'kind': 'file', 'id': 'note.md'},
                    source={'path': 'note.md', 'revision': sha256_text('A local note')},
                    evidence=['note.md'], confidence=0.5, status='current')
        args = {'id': 'queued-owner', 'type': 'decision', 'title': '$(touch bad); literal',
                'file': 'note.md', 'links': ['git:abc', link], 'tags': []}
        with patch.dict('os.environ', {'PMEM_WRITE_LOCK_TIMEOUT_SECONDS': '0'}), MemoryWriteLock(self.root, 'other writer'):
            result = self.call('pmem_knowledge_add', args)['result']['structuredContent']
            self.assertEqual(result['status'], 'queued')
            self.assertFalse(result['completed'])
            self.assertIsNone(result['record'])
            self.assertFalse((self.root / '.project-memory/graph.sqlite').exists())
        item = queue_items(self.root)[0]
        self.assertIn('--project-local', item['argv'])
        self.assertIn('--clear-list=tags', item['argv'])
        self.assertIn('--title=$(touch bad); literal', item['argv'])
        with patch.object(cli, 'root', return_value=self.root), redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(item['argv']), 0)
        self.assertFalse((self.root / 'bad').exists())
        self.assertEqual(load_links(knowledge._store(self.root), 'knowledge', 'queued-owner'), args['links'])

    def test_cli_invalid_json_before_mutation_and_legacy_still_parses(self):
        argv = ['knowledge', 'add', '--type', 'decision', '--title', 'X', '--file', 'note.md', '--links-json', '{broken']
        with patch.object(cli, 'root', return_value=self.root), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                cli.main(argv)
        self.assertFalse((self.root / '.project-memory').exists())
        with patch.object(cli, 'root', return_value=self.root), redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(argv[:-2] + ['--links-json', '[]', '--link', 'git:abc']), 0)
        self.assertEqual(load_links(knowledge._store(self.root), 'knowledge', 'x'), ['git:abc'])

    def test_queue_replay_rechecks_locality(self):
        args = {'type': 'decision', 'title': 'X', 'file': 'note.md'}
        with patch.dict('os.environ', {'PMEM_WRITE_LOCK_TIMEOUT_SECONDS': '0'}), MemoryWriteLock(self.root, 'other'):
            self.assertEqual(self.call('pmem_knowledge_add', args)['result']['structuredContent']['status'], 'queued')
        item = queue_items(self.root)[0]
        with tempfile.TemporaryDirectory() as outside:
            source = Path(outside) / 'external.md'
            source.write_text('External')
            (self.root / 'note.md').unlink()
            (self.root / 'note.md').symlink_to(source)
            with patch.object(cli, 'root', return_value=self.root), redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(item['argv']), 2)
        self.assertFalse((self.root / '.project-memory/graph.sqlite').exists())

    def test_mcp_write_tools_are_marked_mutating(self):
        from tools.project_memory.mcp_tools import TOOLS
        for kind in ('knowledge', 'rationale'):
            for action in ('add', 'update'):
                tool = next(tool for tool in TOOLS if tool['name'] == f'pmem_{kind}_{action}')
                self.assertFalse(tool['annotations']['readOnlyHint'])
                self.assertFalse(tool['inputSchema']['additionalProperties'])

    def test_update_can_explicitly_clear_evidence_and_links(self):
        result = self.call('pmem_rationale_add', {'type': 'decision', 'title': 'Owner', 'file': 'note.md',
                                               'evidence': ['git:abc'], 'links': ['git:abc']})
        self.assertFalse(result['result']['isError'])
        result = self.call('pmem_rationale_update', {'id': 'owner', 'file': 'note.md', 'evidence': [], 'links': []})
        self.assertFalse(result['result']['isError'])
        store = knowledge._store(self.root)
        self.assertEqual(load_links(store, 'rationale', 'owner'), [])
        self.assertEqual(json.loads(store.query("SELECT evidence_json FROM rationale_entries WHERE id='owner'")[0][0]), [])

    def test_real_stdio_mcp_add_update_and_read_with_fallback(self):
        directory = self.root / '.project-memory'
        directory.mkdir()
        (directory / 'config.yaml').write_text('vector:\n  backend: fallback\n')
        requests = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'pmem_knowledge_add',
             'arguments': {'type': 'decision', 'title': 'Wire record', 'id': 'wire', 'file': 'note.md', 'links': ['git:abc']}}},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'pmem_knowledge_update',
             'arguments': {'id': 'wire', 'file': 'note.md'}}},
            {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'pmem_relations',
             'arguments': {'kind': 'knowledge', 'id': 'wire'}}},
            {'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call', 'params': {'name': 'pmem_overview', 'arguments': {}}},
        ]
        env = {**os.environ, 'PYTHONPATH': str(Path(cli.__file__).parents[2]),
               'PYTHONDONTWRITEBYTECODE': '1', 'HF_HUB_OFFLINE': '1'}
        run = subprocess.run([sys.executable, '-m', 'tools.project_memory.cli', 'mcp', '--root', str(self.root)],
                             input='\n'.join(json.dumps(item) for item in requests) + '\n', cwd=self.root,
                             env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(run.returncode, 0, run.stderr)
        results = {row['id']: row['result'] for row in map(json.loads, run.stdout.splitlines())}
        self.assertIn('pmem_rationale_update', {tool['name'] for tool in results[1]['tools']})
        for key in (2, 3, 4, 5):
            self.assertFalse(results[key]['isError'], results[key])
        self.assertEqual(results[3]['structuredContent']['record']['version'], 2)
        self.assertEqual(results[4]['structuredContent']['relations'][0]['link'], 'git:abc')
        self.assertFalse(results[5]['structuredContent']['filesystem_checked'])
