"""Installer instruction contracts; all installs are disposable and outside Desktop."""
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from project_memory_kit.installer.install_project import install_project


class InstructionCoreTest(unittest.TestCase):
    def test_each_client_core_has_an_installed_operations_reference(self):
        for profile in ['codex', 'claude', 'multiagent']:
            with self.subTest(profile=profile), tempfile.TemporaryDirectory(dir='/tmp') as tmp:
                root = Path(tmp)
                result = install_project(root, agent=profile, no_git_init=True)
                self.assertTrue(result.completed, result.summary())
                for name in ['AGENTS.md', 'CLAUDE.md']:
                    file = root / name
                    if not file.exists():
                        continue
                    text = file.read_text()
                    refs = re.findall(r'\[PMEM operations\]\(([^)]+)\)', text)
                    self.assertEqual(len(refs), 1, name)
                    reference = root / refs[0]
                    self.assertTrue(reference.is_file(), str(reference))
                    self.assertIn('pmem_knowledge_add/update', reference.read_text())
                    self.assertIn('qdrant.lock', reference.read_text())
                    self.assertIn('pending', text)
                    self.assertNotIn('## After Editing', text)
                self.assertFalse((root / '.git').exists())

    def test_upgrade_preserves_local_instructions_and_the_short_core(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            (root / 'AGENTS.md').write_text('# Local contract\n\nKeep the user scope.\n')
            result = install_project(root, agent='codex', no_git_init=True)
            self.assertTrue(result.completed, result.summary())
            before = (root / 'AGENTS.md').read_text()
            result = install_project(root, agent='codex', upgrade=True)
            self.assertTrue(result.completed, result.summary())
            after = (root / 'AGENTS.md').read_text()
            self.assertEqual(before, after)
            self.assertIn('Keep the user scope.', after)
            block = after.split('<!-- PMEM:BEGIN -->')[1].split('<!-- PMEM:END -->')[0]
            self.assertLess(len(block), 3000)
            self.assertIn('without an automatic index/impact/tests sequence', block)


class ContextGuidanceTest(unittest.TestCase):
    def test_non_git_context_preserves_diagnostics_without_mandatory_reruns(self):
        from tools.project_memory.services.context_builder import build_context
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            (root / '.project-memory').mkdir()
            (root / '.project-memory/install.json').write_text('{"installation_mode":"non_git_container"}')
            with patch('tools.project_memory.services.context_builder.search', return_value=[]), \
                 patch('tools.project_memory.services.context_builder.search_knowledge', return_value=[]), \
                 patch('tools.project_memory.services.context_builder.search_rationale', return_value=[]):
                text = build_context(root, 'inspect fixture instructions')
            self.assertTrue('unavailable' in text, 'lost non-Git diagnostics')
            self.assertFalse('## Agent Checklist' in text, 'unconditional checklist remains')
            self.assertFalse('Re-run `./pmem index' in text, 'unconditional index rerun remains')
            self.assertFalse('Re-run `./pmem impact' in text, 'unconditional impact rerun remains')
            self.assertTrue('stale or changed' in text, 'missing conditional freshness guidance')
            self.assertTrue('recommendations' in text, 'test commands imply automatic execution')


if __name__ == '__main__':
    unittest.main()
