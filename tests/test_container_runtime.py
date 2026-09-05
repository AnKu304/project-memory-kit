import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.project_memory.ignore import iter_indexable_files, should_index
from tools.project_memory.git_diff import run_git
from tools.project_memory.services.impact_analysis import analyze_impact, format_impact
from tools.project_memory.services.test_selector import select_tests
from tools.project_memory.services.task_gate import gate_report


class ContainerRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'container'
        self.root.mkdir()
        meta = self.root / '.project-memory'
        meta.mkdir()
        (meta / 'install.json').write_text(json.dumps({'installation_mode': 'non_git_container'}))

    def write(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture text')
        return path

    def test_exact_nested_sources_and_hard_exclusions(self):
        wanted = {'code/app.py', 'code/nested/index.ts', 'marketing/plan.md'}
        excluded = {'code/.git/config', 'code/nested/.git/HEAD', 'agent/raw.md', 'archive/old.md',
                    'raw/dump.json', 'backups/copy.py', 'logs/debug.txt', 'screenshots/capture.md',
                    '.project-memory/runtime/cache.py', 'code/runtime.sqlite', 'code/.env'}
        for relative in wanted | excluded:
            self.write(relative)
        with patch('tools.project_memory.ignore.load_config', return_value={'indexing': {
            'ignore': [], 'include_extensions': ['.py', '.ts', '.md', '.json', '.txt']}}):
            paths = {p.relative_to(self.root).as_posix() for p in iter_indexable_files(self.root)}
        self.assertEqual(paths, wanted)

    def test_external_file_symlink_never_read_and_should_index_rejects_outside(self):
        outside = Path(self.tmp.name) / 'outside.py'
        outside.write_text('outside source')
        (self.root / 'escape.py').symlink_to(outside)
        (self.root / 'external-dir').symlink_to(Path(self.tmp.name), target_is_directory=True)
        original = Path.open
        def opened(path, *args, **kwargs):
            if path.resolve() == outside.resolve():
                self.fail('external source was opened')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', opened):
            self.assertEqual(iter_indexable_files(self.root), [])
            self.assertFalse(should_index(self.root, outside))

    def test_git_cannot_fall_back_to_parent_repository(self):
        subprocess.run(['git', 'init', '-q', self.tmp.name], check=True)
        result = run_git(self.root, ['rev-parse', '--show-toplevel'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unavailable', result.stderr.lower())

    def test_non_git_impact_and_tests_do_not_claim_safe_no_changes(self):
        with patch('tools.project_memory.services.impact_analysis.ensure_fresh_index'):
            report = analyze_impact(self.root)
        self.assertFalse(report['git_available'])
        self.assertEqual(report['risk'], 'unknown')
        self.assertEqual(report['impact_status'], 'unavailable')
        text = format_impact(report)
        self.assertIn('unavailable', text.lower())
        self.assertNotIn('No git diff changes detected', text)
        tests = select_tests(self.root, impact=report)
        self.assertTrue(tests.diagnostics)
        evidence = {'index': {'fresh': True}, 'active_tasks': [], 'tests': tests}
        gate = gate_report(evidence, report)
        self.assertFalse(next(c for c in gate['checks'] if c['name'] == 'impact_available')['ok'])

    def test_sensitive_audit_reports_filename_without_reading_contents(self):
        from tools.project_memory.services.secret_scan import scan_secrets
        sensitive = self.write('credentials.json')
        original = Path.open
        def opened(path, *args, **kwargs):
            if path == sensitive:
                self.fail('sensitive file content was read')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', opened):
            findings = scan_secrets(self.root)
        self.assertTrue(any(item.path == 'credentials.json' and item.rule == 'excluded_sensitive_path' for item in findings))

    def test_repository_sources_are_not_subject_to_container_only_excludes(self):
        (self.root / '.project-memory/install.json').write_text('{"installation_mode":"repository"}')
        source = self.write('agent/worker.py')
        self.assertIn(source, iter_indexable_files(self.root))

    def test_context_marks_non_git_impact_unavailable(self):
        from tools.project_memory.services.context_builder import build_context
        self.write('marketing/plan.md')
        with patch('tools.project_memory.services.context_builder.search', return_value=[]), \
             patch('tools.project_memory.services.context_builder.search_knowledge', return_value=[]), \
             patch('tools.project_memory.services.context_builder.search_rationale', return_value=[]):
            text = build_context(self.root, 'marketing plan')
        self.assertIn('unavailable', text)
        self.assertNotIn('No git diff changes detected', text)
        self.assertNotIn('Run `./pmem index --mode full`', text)

    def test_test_explanation_preserves_diagnostics_without_recomputing_impact(self):
        from tools.project_memory.services.test_selector import explain_tests
        report = analyze_impact(self.root)
        with patch('tools.project_memory.services.test_selector.analyze_impact', return_value=report) as impact:
            explanation = explain_tests(self.root)
        self.assertIsInstance(explanation, str)
        self.assertTrue(explanation.diagnostics)
        impact.assert_called_once()

    def test_direct_outside_source_is_rejected(self):
        from tools.project_memory.ignore import confined_path
        with self.assertRaises(ValueError):
            confined_path(self.root, self.root.parent / 'outside.py')


if __name__ == '__main__':
    unittest.main()
