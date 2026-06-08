from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
