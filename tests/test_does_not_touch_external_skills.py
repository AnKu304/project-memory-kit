from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_memory_kit.installer.install_project import install_project


class ExternalSkillsTest(unittest.TestCase):
    def test_external_skills_are_left_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            external = root / ".agents/skills/frontend-design/SKILL.md"
            external.parent.mkdir(parents=True)
            external.write_text("---\nname: frontend-design\n---\n# External\n", encoding="utf-8")
            install_project(root)
            self.assertEqual(
                external.read_text(encoding="utf-8"),
                "---\nname: frontend-design\n---\n# External\n",
            )
            agents = (root / "AGENTS.md").read_text(encoding="utf-8")
            self.assertNotIn("## Available Skills", agents)
            self.assertIn("External skills may also exist", agents)


if __name__ == "__main__":
    unittest.main()

