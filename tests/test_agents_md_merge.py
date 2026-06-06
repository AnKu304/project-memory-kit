from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_memory_kit.installer.agents_md import merge_agents_block
from project_memory_kit.installer.manifest import InstallReport


class AgentsMergeTest(unittest.TestCase):
    def test_replaces_only_managed_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "AGENTS.md"
            path.write_text(
                "before\n\n<!-- PMEM:BEGIN -->\nold\n<!-- PMEM:END -->\n\nafter\n",
                encoding="utf-8",
            )
            merge_agents_block(path, "new block", InstallReport(root))
            content = path.read_text(encoding="utf-8")
            self.assertIn("before", content)
            self.assertIn("after", content)
            self.assertIn("new block", content)
            self.assertNotIn("\nold\n", content)


if __name__ == "__main__":
    unittest.main()

