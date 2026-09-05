from contextlib import redirect_stdout, redirect_stderr, closing
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tools.project_memory import cli, mcp
from tools.project_memory.mcp_tools import TOOLS


class MemoryReadAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for target in ('tools.project_memory.cli.ensure_fresh_index',
                       'tools.project_memory.mcp.index_project',
                       'tools.project_memory.services.auto_index.ensure_fresh_index',
                       'tools.project_memory.vector.qdrant_store.QdrantLocalStore.__init__',
                       'tools.project_memory.services.concurrency.MemoryWriteLock.__enter__'):
            guard = patch(target, side_effect=AssertionError('Read adapter must not write/index/embed'))
            guard.start()
            self.addCleanup(guard.stop)

    def run_cli(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(cli, 'root', return_value=self.root), redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def call(self, name, args):
        return mcp._handle_request(self.root, dict(jsonrpc='2.0', id=1, method='tools/call',
                                                  params={'name': name, 'arguments': args}))

    def fixture(self):
        from tools.project_memory.hashing import sha256_text
        from tools.project_memory.services.memory_relations import save_links
        from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
        store = SQLiteGraphStore(self.root, self.root / '.project-memory/graph.sqlite')
        # Fixture schema only, no models or installed project.
        schema = Path(__import__('tools.project_memory.graph.sqlite_store', fromlist=['x']).__file__).with_name('schema.sql').read_text()
        with closing(store.connect()) as conn, conn:
            conn.executescript(schema)
            conn.execute("INSERT INTO knowledge_entries(id,type,title,path,content_hash,created_at,updated_at) VALUES ('owner','decision','Owner','owner.md','hash','now','now')")
        (self.root / 'owner.md').write_text('Owner')
        (self.root / 'source.md').write_text('Source')
        link = {'relation': 'affects', 'target': {'kind': 'file', 'id': 'source.md'},
                'source': {'path': 'source.md', 'revision': sha256_text('Source')},
                'confidence': 0.5, 'evidence': ['source.md'], 'status': 'current'}
        save_links(store, 'knowledge', 'owner', [link, 'git:abc'])
        return store

    def test_cli_missing_database_does_not_create_anything(self):
        for args in (['overview'], ['relations', '--kind', 'knowledge', '--id', 'owner']):
            code, output, error = self.run_cli(args)
            self.assertEqual(code, 0, error)
            self.assertEqual(json.loads(output)['status'], 'missing')
            self.assertEqual(list(self.root.iterdir()), [])

    def test_memory_handlers_resolve_cli_root_at_invocation(self):
        self.fixture()
        args = cli.build_parser().parse_args(['relations', '--kind', 'knowledge', '--id', 'owner'])
        output = io.StringIO()
        with patch.object(cli, 'root', return_value=self.root), redirect_stdout(output):
            self.assertEqual(args.func(args), 0)
        self.assertEqual(json.loads(output.getvalue())['status'], 'found')

    def test_mcp_registry_and_missing_database(self):
        names = {tool['name'] for tool in TOOLS}
        self.assertTrue({'pmem_overview', 'pmem_relations', 'pmem_search', 'pmem_knowledge_show'} <= names)
        self.assertEqual(names, set(mcp.TOOL_HANDLERS))
        for name, args in [('pmem_overview', {}), ('pmem_relations', {'kind': 'knowledge', 'id': 'owner'})]:
            response = self.call(name, args)
            self.assertFalse(response['result']['isError'])
            self.assertEqual(response['result']['structuredContent']['status'], 'missing')
        self.assertEqual(list(self.root.iterdir()), [])

    def test_cli_and_mcp_same_results_and_truncation(self):
        self.fixture()
        for command, tool, args, params in [
            ('overview', 'pmem_overview', ['--limit', '1'], {'limit': 1}),
            ('relations', 'pmem_relations', ['--kind', 'knowledge', '--id', 'owner', '--limit', '1'],
             {'kind': 'knowledge', 'id': 'owner', 'limit': 1}),
        ]:
            code, output, error = self.run_cli([command, *args])
            self.assertEqual(code, 0, error)
            self.assertEqual(json.loads(output), self.call(tool, params)['result']['structuredContent'])
        payload = self.call('pmem_relations', {'kind': 'knowledge', 'id': 'owner', 'limit': 1})['result']['structuredContent']
        self.assertTrue(payload['truncated'])
        self.assertEqual(payload['relations'][0]['source_revision_status'], 'matches')
        self.assertFalse(payload['relations'][0]['verified'])

    def test_invalid_mcp_arguments_rejected_without_io(self):
        for name, args in [('pmem_overview', {'limit': True}), ('pmem_overview', {'limit': 101}),
                           ('pmem_overview', {'shared': True}), ('pmem_relations', {'kind': 'other', 'id': 'owner'}),
                           ('pmem_relations', {'kind': 'knowledge', 'id': '../owner'}),
                           ('pmem_relations', {'kind': 'knowledge', 'id': 'owner', 'root': '/tmp'})]:
            with self.subTest(name=name, args=args):
                self.assertTrue(self.call(name, args)['result']['isError'])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_readonly_connection_and_foreign_database(self):
        from tools.project_memory.read_adapters import _ReadOnlyGraphStore
        store = self.fixture()
        reader = _ReadOnlyGraphStore(self.root, store.db_path)
        with closing(reader.connect()) as conn:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute('DELETE FROM knowledge_entries')
        with tempfile.TemporaryDirectory() as foreign:
            other = Path(foreign)
            (other / '.project-memory').mkdir()
            (other / '.project-memory/graph.sqlite').symlink_to(store.db_path)
            with patch.object(cli, 'root', return_value=other):
                response = mcp._handle_tool_call(other, 1, {'name': 'pmem_relations', 'arguments': {'kind': 'knowledge', 'id': 'owner'}})
            self.assertTrue(response['result']['isError'])

    def test_empty_test_selection_diagnostics_reach_cli_and_mcp(self):
        class Selection(list):
            diagnostics = ['Git-specific selection unavailable']
        selected = Selection()
        with patch.object(cli, 'select_tests', return_value=selected):
            code, output, _ = self.run_cli(['tests'])
        self.assertEqual(code, 0)
        self.assertIn(selected.diagnostics[0], output)
        with patch.object(mcp, 'select_tests', return_value=selected):
            response = self.call('pmem_tests', {})['result']
        self.assertEqual(response['structuredContent']['commands'], [])
        self.assertEqual(response['structuredContent']['diagnostics'], selected.diagnostics)
        self.assertIn(selected.diagnostics[0], response['content'][0]['text'])

    def test_explain_diagnostics_use_existing_explanation_without_second_selection(self):
        class Explanation(str):
            diagnostics = ['Git-specific selection unavailable']
        explanation = Explanation('Warning: Git-specific selection unavailable')
        with patch.object(mcp, 'explain_tests', return_value=explanation) as explain, patch.object(mcp, 'select_tests', side_effect=AssertionError('duplicate selection')):
            result = self.call('pmem_tests', {'explain': True})['result']['structuredContent']
        explain.assert_called_once()
        self.assertEqual(result['diagnostics'], explanation.diagnostics)
