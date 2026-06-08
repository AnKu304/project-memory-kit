from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from project_memory_kit.version import __version__


class NpmDistributionTest(unittest.TestCase):
    def test_node_wrapper_runs_cli_and_installs_project(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        wrapper = repo / "npm/bin/pmem.js"

        version = subprocess.run(
            ["node", str(wrapper), "version"],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(version.returncode, 0, version.stderr)
        self.assertEqual(version.stdout.strip(), __version__)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install = subprocess.run(
                ["node", str(wrapper), "init", "--target", str(root), "--agent", "multiagent"],
                cwd=repo,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(install.returncode, 0, install.stderr)
            self.assertTrue((root / "pmem").exists())
            self.assertTrue((root / "AGENTS.md").exists())
            self.assertTrue((root / "CLAUDE.md").exists())
            self.assertTrue((root / ".claude/agents/pmem-coordinator.md").exists())
            self.assertTrue((root / ".agents/tasks/_templates/user-task.md").exists())
            self.assertTrue((root / ".claude/settings.json").exists())

    def test_npm_package_metadata_and_pack_contents_are_publish_ready(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        package = json.loads((repo / "package.json").read_text(encoding="utf-8"))

        self.assertEqual(package["version"], __version__)
        self.assertEqual(package["type"], "commonjs")
        self.assertEqual(package["publishConfig"]["access"], "public")
        self.assertIn("smoke", package["scripts"])
        self.assertIn("pack:check", package["scripts"])
        self.assertIn("prepack", package["scripts"])

        check = subprocess.run(
            ["node", "npm/scripts/check-pack.js"],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("npm pack check ok", check.stdout)


if __name__ == "__main__":
    unittest.main()
