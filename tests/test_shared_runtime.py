from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
import sqlite3
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from project_memory_kit.installer.install_project import install_project, uninstall_project
from project_memory_kit.installer.shared_launcher import resolve_binding
from project_memory_kit.installer.shared_runtime import bind_shared_runtime, install_shared_runtime


class SharedRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="pmem-shared-contract-")
        cls.base = Path(cls.temporary.name).resolve()
        cls.shared = cls.base / "shared"
        install_shared_runtime(cls.shared, install_dependencies=False)
        # Isolated launch deliberately excludes user-site modules. Supply existing
        # test dependencies in the fixture venv, without network installation.
        import yaml
        site_packages = next((cls.shared / ".venv/lib").glob("python*/site-packages"))
        for module in (yaml,):
            shutil.copytree(Path(module.__file__).parent, site_packages / module.__name__, dirs_exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def project(self, name):
        root = self.base / name
        root.mkdir()
        (root / "source.md").write_text("# Project source\n", encoding="utf-8")
        install_project(root)
        return root

    def run_pmem(self, root, *args, cwd=None):
        return subprocess.run([str(root / "pmem"), *args], cwd=cwd or root, capture_output=True, text=True)

    def test_one_runtime_preserves_two_isolated_databases_and_works_outside_project(self):
        first = self.project("one")
        second = self.project("two")
        original = {}
        for root in [first, second]:
            connection = sqlite3.connect(root / ".project-memory/graph.sqlite")
            connection.execute("CREATE TABLE isolation_probe(value TEXT)")
            connection.execute("INSERT INTO isolation_probe VALUES(?)", (root.name,))
            connection.commit()
            connection.close()
            original[root] = (root / ".project-memory/graph.sqlite").read_bytes()
            bind_shared_runtime(root, self.shared)
            self.assertTrue((root / "tools/project_memory").is_symlink())
            self.assertEqual(original[root], (root / ".project-memory/graph.sqlite").read_bytes())
            doctor = self.run_pmem(root, "doctor", cwd=self.base)
            self.assertEqual(doctor.returncode, 0, doctor.stderr + doctor.stdout)
            self.assertIn(str(root), doctor.stdout)
        self.assertEqual((first / "tools/project_memory").resolve(), (second / "tools/project_memory").resolve())
        registry = json.loads((self.shared / "projects.json").read_text())
        self.assertTrue({str(first), str(second)}.issubset({entry["project_root"] for entry in registry["projects"].values()}))

    def test_bound_wrapper_rejects_sibling_root_and_registry_mismatch(self):
        root = self.project("boundary")
        sibling = self.project("sibling")
        bind_shared_runtime(root, self.shared)
        for args in [("mcp", "--root", str(sibling)), ("mcp", "--roo", str(sibling)), ("mcp", f"--root={sibling}"), ("mcp-config", "--root", str(sibling))]:
            response = self.run_pmem(root, *args)
            self.assertEqual(response.returncode, 2, response.stdout + response.stderr)
            self.assertIn("registered memory root", response.stderr)
        binding = json.loads((root / ".project-memory/runtime-binding.json").read_text())
        with self.assertRaises((ValueError, OSError)):
            resolve_binding(self.shared, sibling, binding["binding_id"])
        binding["project_root"] = str(sibling)
        (root / ".project-memory/runtime-binding.json").write_text(json.dumps(binding))
        response = self.run_pmem(root, "version")
        self.assertEqual(response.returncode, 2)

    def test_upgrade_and_rebind_keep_runtime_shared_and_backup_once(self):
        root = self.project("upgrade-shared")
        bind_shared_runtime(root, self.shared)
        archives = list((root / ".project-memory/runtime-backups").glob("*.tar.gz"))
        self.assertEqual(len(archives), 1)
        install_project(root, upgrade=True, agent="auto")
        bind_shared_runtime(root, self.shared)
        self.assertTrue((root / "tools/project_memory").is_symlink())
        self.assertEqual(list((root / ".project-memory/runtime-backups").glob("*.tar.gz")), archives)
        metadata = json.loads((root / ".project-memory/install.json").read_text())
        self.assertEqual(metadata["runtime_layout"], "shared")
        self.assertEqual(self.run_pmem(root, "version").returncode, 0)

    def test_uninstall_compatibility_link_does_not_delete_shared_code(self):
        root = self.project("uninstall-shared")
        bind_shared_runtime(root, self.shared)
        code = (root / "tools/project_memory").resolve()
        uninstall_project(root)
        self.assertTrue((code / "cli.py").exists())
        self.assertTrue((root / ".project-memory/graph.sqlite").exists())
        self.assertFalse((root / "tools/project_memory").is_symlink())

    def test_bind_requires_installed_project_and_rejects_symlink_state(self):
        root = self.base / "unregistered"
        root.mkdir()
        with self.assertRaises(OSError):
            bind_shared_runtime(root, self.shared)
        source = self.project("real-state")
        (root / ".project-memory").symlink_to(source / ".project-memory", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            bind_shared_runtime(root, self.shared)

    def test_new_project_installs_directly_against_shared_runtime(self):
        root = self.base / "new-direct"
        root.mkdir()
        (root / "source.py").write_text("def shared_source(): return True\n")
        result = install_project(root, shared_runtime=self.shared)
        self.assertTrue(result.completed)
        self.assertTrue((root / "tools/project_memory").is_symlink())
        self.assertTrue((root / ".project-memory/graph.sqlite").exists())
        self.assertTrue((root / ".project-memory/runtime/.venv").is_symlink())
        self.assertFalse((root / ".project-memory/runtime-backups").exists())
        legacy = subprocess.run([str(root / ".project-memory/runtime/.venv/bin/python"), "-m", "tools.project_memory.cli", "version"], cwd=root, capture_output=True, text=True)
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        self.assertEqual(legacy.stdout, self.run_pmem(root, "version").stdout)
        import yaml
        configuration = yaml.safe_load((root / ".project-memory/config.yaml").read_text())
        self.assertEqual(configuration["code_provider"], {"backend": "gitnexus", "repositories": []})
        self.assertFalse(configuration["indexing"]["auto_index"]["enabled"])
        context = self.run_pmem(root, "context", "--task", "planning")
        self.assertEqual(context.returncode, 0, context.stdout + context.stderr)
        with closing(sqlite3.connect(root / ".project-memory/graph.sqlite")) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM file_index_state").fetchone()[0], 0)

    def test_failed_doctor_restores_registry_wrappers_and_local_runtime(self):
        root = self.project("rollback")
        previous_wrapper = (root / "pmem").read_bytes()
        previous_registry = (self.shared / "projects.json").read_bytes()
        original_run = subprocess.run

        def failing_doctor(command, *args, **kwargs):
            if command == [str(root / "pmem"), "doctor"]:
                return subprocess.CompletedProcess(command, 1, "broken doctor", "")
            return original_run(command, *args, **kwargs)

        with patch("project_memory_kit.installer.shared_runtime.subprocess.run", side_effect=failing_doctor):
            with self.assertRaisesRegex(ValueError, "doctor failed"):
                bind_shared_runtime(root, self.shared)
        self.assertEqual(previous_wrapper, (root / "pmem").read_bytes())
        self.assertEqual(previous_registry, (self.shared / "projects.json").read_bytes())
        self.assertFalse((root / ".project-memory/runtime-binding.json").exists())
        self.assertTrue((root / "tools/project_memory/cli.py").is_file())
        self.assertFalse((root / "tools/project_memory").is_symlink())

    def test_live_legacy_project_consumer_blocks_retirement(self):
        import sys
        root = self.project("live-legacy")
        process = subprocess.Popen([sys.executable, "-m", "tools.project_memory.cli", "mcp", "--root", str(root)], cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            with self.assertRaisesRegex(ValueError, "Legacy PMEM consumer"):
                bind_shared_runtime(root, self.shared)
            self.assertFalse((root / "tools/project_memory").is_symlink())
        finally:
            process.terminate()
            process.communicate(timeout=10)
