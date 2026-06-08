from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from project_memory_kit.installer.install_project import install_project


class InstallProfilesTest(unittest.TestCase):
    def test_claude_profile_installs_claude_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root, agent="claude")

            self.assertFalse((root / "AGENTS.md").exists())
            self.assertTrue((root / "CLAUDE.md").exists())
            self.assertTrue((root / ".claude/rules/project-memory.md").exists())
            self.assertTrue((root / ".claude/skills/dependency-graph-rag/SKILL.md").exists())
            self.assertTrue((root / ".claude/commands/pmem-context.md").exists())
            self.assertFalse((root / ".claude/agents/pmem-coordinator.md").exists())

            metadata = json.loads((root / ".project-memory/install.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["agent_profile"], "claude")
            self.assertIn("CLAUDE.md", metadata["managed_paths"])

    def test_multiagent_profile_installs_codex_claude_and_role_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root, agent="multiagent")

            self.assertTrue((root / "AGENTS.md").exists())
            self.assertTrue((root / "CLAUDE.md").exists())
            self.assertTrue((root / ".agents/skills/dependency-graph-rag/SKILL.md").exists())
            self.assertTrue((root / ".agents/roles/README.md").exists())
            self.assertTrue((root / ".claude/skills/dependency-graph-rag/SKILL.md").exists())
            self.assertTrue((root / ".claude/agents/pmem-coordinator.md").exists())

            metadata = json.loads((root / ".project-memory/install.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["agent_profile"], "multiagent")
            self.assertIn(".claude/agents/", metadata["managed_paths"])

    def test_universal_alias_maps_to_multiagent_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root, agent="universal")
            metadata = json.loads((root / ".project-memory/install.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["agent_profile"], "multiagent")


if __name__ == "__main__":
    unittest.main()
