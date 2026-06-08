from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from project_memory_kit.cli import init_command
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
            self.assertTrue((root / ".claude/settings.json").exists())
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
            self.assertTrue((root / ".agents/rules/security.md").exists())
            self.assertTrue((root / ".agents/roles/README.md").exists())
            self.assertTrue((root / ".agents/tasks/_templates/user-task.md").exists())
            self.assertTrue((root / ".claude/skills/dependency-graph-rag/SKILL.md").exists())
            self.assertTrue((root / ".claude/agents/pmem-coordinator.md").exists())

            metadata = json.loads((root / ".project-memory/install.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["agent_profile"], "multiagent")
            self.assertEqual(metadata["agent_profiles"], ["codex", "claude", "multiagent"])
            self.assertIn(".claude/agents/", metadata["managed_paths"])

    def test_universal_alias_maps_to_multiagent_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root, agent="universal")
            metadata = json.loads((root / ".project-memory/install.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["agent_profile"], "multiagent")

    def test_interactive_init_applies_scripted_choices(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            answers = iter(["codex", "yes", "yes", "fallback", "yes"])

            with contextlib.redirect_stdout(io.StringIO()):
                init_command(
                    target=str(root),
                    interactive=True,
                    input_func=lambda _: next(answers),
                )

            metadata = json.loads((root / ".project-memory/install.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["agent_profile"], "multiagent")
            self.assertTrue((root / ".agents/tasks/_templates/user-task.md").exists())
            self.assertTrue((root / ".agents/roles/README.md").exists())
            config = (root / ".project-memory/config.yaml").read_text(encoding="utf-8")
            self.assertIn("backend: fallback", config)
            self.assertIn("human:\n    enabled: true", config)
            self.assertTrue((root / ".project-memory/human").exists())
            self.assertTrue((root / ".project-memory/reports/codex-mcp-config.toml").exists())

    def test_profile_upgrade_preserves_memory_and_tracks_installed_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("def saved():\n    return True\n", encoding="utf-8")
            install_project(root, agent="codex")
            subprocess.run(
                [str(root / "pmem"), "index", "--mode", "full"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            before = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                before_count = before.execute("SELECT count(*) FROM nodes").fetchone()[0]
            finally:
                before.close()

            install_project(root, agent="claude", upgrade=True)

            self.assertTrue((root / "AGENTS.md").exists())
            self.assertTrue((root / "CLAUDE.md").exists())
            metadata = json.loads((root / ".project-memory/install.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["agent_profile"], "claude")
            self.assertEqual(metadata["agent_profiles"], ["codex", "claude"])
            after = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                after_count = after.execute("SELECT count(*) FROM nodes").fetchone()[0]
            finally:
                after.close()
            self.assertEqual(before_count, after_count)


if __name__ == "__main__":
    unittest.main()
