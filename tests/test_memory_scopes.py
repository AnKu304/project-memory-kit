from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.project_memory.services.memory_scope import classify_memory_path


class MemoryScopeTests(unittest.TestCase):
    def test_nested_paths_keep_domain_separate_from_audience(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = classify_memory_path(root, 'apps/frontend/components/Button.tsx', {})
            tooling = classify_memory_path(root, '.agents/skills/frontend/SKILL.md', {})
            self.assertEqual(project, dict(memory_scope='project', memory_audience='project',
                                           memory_type='code', memory_domain='frontend'))
            self.assertEqual(tooling, dict(memory_scope='project', memory_audience='agent_tooling',
                                           memory_type='agent_tooling', memory_domain='frontend'))
            unknown = classify_memory_path(root, 'notes/random.md', {})
            self.assertEqual(unknown['memory_domain'], 'unclassified')
            self.assertEqual(unknown['memory_type'], 'document')

    def test_config_first_match_overrides_defaults_and_allows_declared_domain(self):
        cfg = {'memory': {'classification': {'domains': ['analytics'], 'rules': [
            {'pattern': 'apps/frontend/research/**', 'domain': 'analytics', 'type': 'knowledge'},
            {'pattern': 'apps/frontend/**', 'domain': 'backend'},
        ]}}}
        with tempfile.TemporaryDirectory() as directory:
            result = classify_memory_path(Path(directory), 'apps/frontend/research/study.md', cfg)
        self.assertEqual(result['memory_domain'], 'analytics')
        self.assertEqual(result['memory_type'], 'knowledge')
        self.assertEqual(result['memory_audience'], 'project')

    def test_knowledge_rationale_and_domain_are_orthogonal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for memory_type in ('knowledge', 'rationale'):
                result = classify_memory_path(root, f'.project-memory/{memory_type}/design/note.md', {})
                self.assertEqual(result['memory_type'], memory_type)
                self.assertEqual(result['memory_domain'], 'design')
                self.assertEqual(result['memory_audience'], 'project')
            configured = classify_memory_path(root, 'docs/decisions/backend/db.md',
                {'paths': {'rationale_dir': 'docs/decisions'}})
            self.assertEqual(configured['memory_type'], 'rationale')
            self.assertEqual(configured['memory_domain'], 'backend')

    def test_invalid_paths_and_rules_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            (root / 'external').symlink_to(outside, target_is_directory=True)
            for path in ('../other.py', 'foo/../bar.py', '', '.', 'external/file.py', outside, 'C:\\other.py'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    classify_memory_path(root, path, {})
            for rule in ({'scope': 'shared'}, {'domain': 'invented'}, {'type': 'wrong'}, {'audience': 'all'}):
                cfg = {'memory': {'classification': {'rules': [{'pattern': '**', **rule}]}}}
                with self.subTest(rule=rule), self.assertRaises(ValueError):
                    classify_memory_path(root, 'safe.py', cfg)

    def test_actual_index_persists_all_axes_without_changing_legacy_layer(self):
        from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
        from tools.project_memory.services.index_project import index_project
        from tools.project_memory.vector.qdrant_store import QdrantLocalStore
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path, content in {
                'frontend/app.py': 'def render():\n    return 1\n',
                '.agents/skills/design/SKILL.md': 'Design instructions',
            }.items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            def vectors(*args, **kwargs):
                return QdrantLocalStore(*args, **{**kwargs, 'backend': 'fallback'})
            with patch('tools.project_memory.services.index_project.QdrantLocalStore', side_effect=vectors):
                self.assertIn('indexed=2', index_project(root, 'full'))
                self.assertIn('skipped=2', index_project(root, 'changed'))
            graph = SQLiteGraphStore(root, root / '.project-memory/graph.sqlite')
            nodes = graph.query("SELECT path, kind, layer, properties_json FROM nodes WHERE path != '.'")
            self.assertTrue(nodes)
            for node in nodes:
                metadata = classify_memory_path(root, node['path'], {})
                props = json.loads(node['properties_json'])
                self.assertEqual({key: props[key] for key in metadata}, metadata)
                self.assertIsNone(node['layer'])
                if node['kind'] == 'Chunk':
                    self.assertIn('content', props)
            vector_file = root / '.project-memory/qdrant/fallback_chunks.jsonl'
            for line in vector_file.read_text().splitlines():
                payload = json.loads(line)['payload']
                metadata = classify_memory_path(root, payload['file_path'], {})
                self.assertEqual({key: payload[key] for key in metadata}, metadata)

    def test_import_placeholder_does_not_erase_indexed_file_metadata(self):
        from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
        from tools.project_memory.services.index_project import index_project
        from tools.project_memory.vector.qdrant_store import QdrantLocalStore
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'alpha.ts').write_text('export function helper() { return 1; }\n')
            def vectors(*args, **kwargs):
                return QdrantLocalStore(*args, **{**kwargs, 'backend': 'fallback'})
            with patch('tools.project_memory.services.index_project.QdrantLocalStore', side_effect=vectors):
                index_project(root, 'full')
                graph = SQLiteGraphStore(root, root / '.project-memory/graph.sqlite')
                previous = graph.query("SELECT * FROM nodes WHERE kind='File' AND path='alpha.ts'")[0]
                original_props = {**json.loads(previous['properties_json']), 'sentinel': 'keep', 'component_boundary': 'client'}
                with graph.connect() as connection:
                    connection.execute("UPDATE nodes SET properties_json=?, layer='frontend' WHERE id=?",
                                       (json.dumps(original_props), previous['id']))
                (root / 'beta.ts').write_text('import { helper } from "./alpha";\nexport function run() { return helper(); }\n')
                index_project(root, 'changed')
            current = graph.query("SELECT * FROM nodes WHERE kind='File' AND path='alpha.ts'")[0]
            props = json.loads(current['properties_json'])
            self.assertEqual(props['memory_type'], 'code')
            self.assertEqual(props, original_props)
            self.assertEqual(current['hash'], previous['hash'])
            self.assertEqual(current['layer'], 'frontend')

    def test_changed_index_applies_new_rules_even_outside_git_changed_paths(self):
        from tools.project_memory.services.index_project import index_project
        from tools.project_memory.vector.qdrant_store import QdrantLocalStore
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'alpha.py').write_text('def helper():\n    return 1\n')
            (root / 'beta.py').write_text('def other():\n    return 2\n')
            def vectors(*args, **kwargs):
                return QdrantLocalStore(*args, **{**kwargs, 'backend': 'fallback'})
            with patch('tools.project_memory.services.index_project.QdrantLocalStore', side_effect=vectors):
                index_project(root, 'full')
                cfg = {'memory': {'classification': {'rules': [{'pattern': 'alpha.py', 'domain': 'backend'}]}}}
                with patch('tools.project_memory.git_diff.changed_files', return_value=['beta.py']), patch(
                    'tools.project_memory.git_diff.untracked_files', return_value=[]
                ), patch('tools.project_memory.services.index_project.load_config', return_value=cfg
                ):
                    self.assertIn('indexed=1', index_project(root, 'changed'))
            records = [json.loads(line)['payload'] for line in
                       (root / '.project-memory/qdrant/fallback_chunks.jsonl').read_text().splitlines()]
            self.assertEqual(next(row for row in records if row['file_path'] == 'alpha.py')['memory_domain'], 'backend')

    def test_invalid_scope_is_rejected_before_database_is_created(self):
        from tools.project_memory.services.index_project import index_project
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = {'memory': {'classification': {'rules': [{'pattern': '**', 'scope': 'shared'}]}}}
            with patch('tools.project_memory.services.index_project.load_config', return_value=cfg), self.assertRaises(ValueError):
                index_project(root, 'full')
            self.assertFalse((root / '.project-memory/graph.sqlite').exists())


if __name__ == '__main__':
    unittest.main()
