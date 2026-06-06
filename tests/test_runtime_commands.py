from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from project_memory_kit.installer.install_project import install_project


class RuntimeCommandsTest(unittest.TestCase):
    def test_context_and_search_work_after_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root)
            (root / "app.py").write_text("def pay(amount):\n    return amount > 0\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py"], cwd=root)
            subprocess.run(["git", "commit", "-m", "init"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            install_project(root)

            (root / "app.py").write_text("def pay(amount):\n    return amount >= 0\n", encoding="utf-8")
            subprocess.run(
                [str(root / "pmem"), "index", "--mode", "full"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            context = subprocess.run(
                [
                    str(root / "pmem"),
                    "context",
                    "--task",
                    "change payment validation",
                    "--base",
                    "HEAD",
                    "--out",
                    ".project-memory/reports/CHANGE_CONTEXT.md",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
            )
            self.assertEqual(context.returncode, 0, context.stdout)
            content = (root / ".project-memory/reports/CHANGE_CONTEXT.md").read_text(encoding="utf-8")
            self.assertIn("# Change Context", content)
            self.assertIn("## Agent Checklist", content)


if __name__ == "__main__":
    unittest.main()
