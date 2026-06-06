from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_memory_kit.installer.gitignore import merge_gitignore
from project_memory_kit.installer.manifest import InstallReport


class GitignoreMergeTest(unittest.TestCase):
    def test_replaces_project_memory_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / ".gitignore"
            path.write_text("node_modules/\n\n# PMEM:BEGIN\nold\n# PMEM:END\n", encoding="utf-8")
            merge_gitignore(path, ".project-memory/graph.sqlite", InstallReport(root))
            content = path.read_text(encoding="utf-8")
            self.assertIn("node_modules/", content)
            self.assertIn(".project-memory/graph.sqlite", content)
            self.assertNotIn("\nold\n", content)


if __name__ == "__main__":
    unittest.main()

