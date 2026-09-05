from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from project_memory_kit.installer.install_project import install_project
from project_memory_kit import cli


class NonGitInstallerTest(unittest.TestCase):
    def test_container_install_and_upgrade_never_initialize_git(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp) / 'container space'
            root.mkdir()
            (root / 'marketing').mkdir()
            (root / 'marketing/brief.md').write_text('A fixture marketing brief')
            (root / 'code').mkdir()
            subprocess.run(['git', 'init', '-q', str(root / 'code')], check=True)
            (root / 'code/app.py').write_text('answer = 42\n')
            install_project(root, no_git_init=True)
            self.assertFalse((root / '.git').exists())
            metadata = json.loads((root / '.project-memory/install.json').read_text())
            self.assertEqual(metadata['installation_mode'], 'non_git_container')
            for command in ['init', 'doctor']:
                result = subprocess.run([str(root / 'pmem'), command], cwd=root, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            install_project(root, upgrade=True, agent='auto')
            self.assertFalse((root / '.git').exists())
            self.assertTrue((root / 'code/.git').exists())
            self.assertEqual(json.loads((root / '.project-memory/install.json').read_text())['installation_mode'], 'non_git_container')
            self.assertEqual((root / 'marketing/brief.md').read_text(), 'A fixture marketing brief')
            ignore = (root / '.project-memoryignore').read_text().splitlines()
            self.assertIn('agent/', ignore)
            self.assertIn('archive/', ignore)
            self.assertIn('*.sqlite', ignore)

    def test_legacy_default_still_creates_git(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            install_project(root)
            self.assertTrue((root / '.git').exists())
            self.assertEqual(json.loads((root / '.project-memory/install.json').read_text())['installation_mode'], 'repository')

    def test_container_inside_git_rejected_before_install(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            parent = Path(tmp)
            subprocess.run(['git', 'init', '-q', str(parent)], check=True)
            target = parent / 'nested'
            with self.assertRaisesRegex(ValueError, 'outside'):
                install_project(target, no_git_init=True)
            self.assertFalse(target.exists())

    def test_corrupt_mode_metadata_cannot_fall_back_to_git_init(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            (root / '.project-memory').mkdir()
            (root / '.project-memory/install.json').write_text('{broken')
            with self.assertRaises(ValueError):
                install_project(root, upgrade=True)
            self.assertFalse((root / '.git').exists())

    def test_argparse_requires_explicit_container_root(self):
        with self.assertRaises(SystemExit):
            cli._argparse_main(['init', '--no-git-init'])
        with patch.object(cli, 'init_command') as init:
            self.assertEqual(cli._argparse_main(['init', '--target', '/tmp/fixture-root', '--no-git-init']), 0)
        self.assertTrue(init.call_args.kwargs['no_git_init'])

    def test_opt_in_forwarded_to_installer(self):
        with patch.object(cli, 'install_project') as install:
            cli.init_command(target='/tmp/fixture-root', no_git_init=True)
        self.assertTrue(install.call_args.kwargs['no_git_init'])

    def test_interrupted_container_install_preserves_mode_for_upgrade(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            with patch('project_memory_kit.installer.install_project.copy_tree', side_effect=RuntimeError('fixture interruption')):
                with self.assertRaises(RuntimeError):
                    install_project(root, no_git_init=True)
            self.assertEqual(json.loads((root / '.project-memory/install.json').read_text())['installation_mode'], 'non_git_container')
            install_project(root, upgrade=True)
            self.assertFalse((root / '.git').exists())

    def test_existing_repository_mode_cannot_convert(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            (root / '.project-memory').mkdir()
            (root / '.project-memory/install.json').write_text(json.dumps({'package':'project-memory-kit', 'installation_mode':'repository'}))
            with self.assertRaisesRegex(ValueError, 'converted'):
                install_project(root, no_git_init=True)
            self.assertFalse((root / 'pmem').exists())

    def test_ignore_file_user_content_survives_upgrade(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            original = '# user policy\ncustom-cache/\n'
            (root / '.project-memoryignore').write_text(original)
            install_project(root, no_git_init=True)
            before = (root / '.project-memoryignore').read_text()
            install_project(root, upgrade=True)
            self.assertTrue(before.startswith(original))
            self.assertEqual((root / '.project-memoryignore').read_text(), before)

    def test_failed_required_runtime_keeps_container_pending(self):
        import importlib
        installer = importlib.import_module('project_memory_kit.installer.install_project')
        for failed_command in ['init', 'migrate', 'doctor']:
            with self.subTest(command=failed_command), tempfile.TemporaryDirectory(dir='/tmp') as tmp:
                root = Path(tmp)
                original_run = subprocess.run
                def run(args, **kwargs):
                    if 'tools.project_memory.cli' in args:
                        # No observable completed metadata during any required command.
                        self.assertTrue(json.loads((root / '.project-memory/install.json').read_text()).get('installation_pending'))
                        code = 1 if args[-1] == failed_command else 0
                        return subprocess.CompletedProcess(args, code, '', 'fixture runtime failed' if code else '')
                    return original_run(args, **kwargs)
                with patch.object(installer.subprocess, 'run', side_effect=run):
                    result = install_project(root, no_git_init=True, run_index=True)
                metadata = json.loads((root / '.project-memory/install.json').read_text())
                self.assertTrue(metadata['installation_pending'])
                self.assertEqual(metadata['installation_mode'], 'non_git_container')
                self.assertFalse(result.completed)
                self.assertTrue(any(f'./pmem {failed_command} failed:' in item for item in result.report.commands))
                self.assertFalse(any('index --mode full' in item for item in result.report.commands))

    def test_pending_install_returns_failure_from_package_cli(self):
        from project_memory_kit.installer.install_project import ProjectInstallResult
        from project_memory_kit.installer.manifest import InstallReport
        report = InstallReport(target=Path('/tmp/fixture'))
        report.commands.append('./pmem init failed: fixture runtime failed')
        with patch.object(cli, 'install_project', return_value=ProjectInstallResult(report, completed=False)):
            with self.assertRaises(SystemExit) as error:
                cli.init_command(target='/tmp/fixture', no_git_init=True)
        self.assertEqual(error.exception.code, 1)


if __name__ == '__main__':
    unittest.main()
