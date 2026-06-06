from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_memory_kit.installer.install_project import install_project


class ExistingAgentsTest(unittest.TestCase):
    def test_preserves_existing_agents_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = "# AGENTS.md\n\nKeep this project rule.\n"
            (root / "AGENTS.md").write_text(original, encoding="utf-8")
            install_project(root)
            content = (root / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Keep this project rule.", content)
            self.assertIn("<!-- PMEM:BEGIN -->", content)
            self.assertIn("Local Project Memory Protocol", content)
            self.assertIn("<!-- PMEM:END -->", content)
            self.assertNotIn("This file is the project instruction hub", content)


if __name__ == "__main__":
    unittest.main()
