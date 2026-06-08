from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from project_memory_kit.version import CONFIG_SCHEMA_VERSION, __version__


ROOT = Path(__file__).resolve().parents[1]


class QualityGuardsTest(unittest.TestCase):
    def test_versions_stay_synchronized(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        runtime = (ROOT / "src/project_memory_kit/installer/runtime/tools/project_memory/version.py").read_text(
            encoding="utf-8"
        )
        init = (ROOT / "src/project_memory_kit/__init__.py").read_text(encoding="utf-8")

        self.assertIn(f'version = "{__version__}"', pyproject)
        self.assertEqual(package["version"], __version__)
        self.assertIn(f'__version__ = "{__version__}"', runtime)
        self.assertIn(f'__version__ = "{__version__}"', init)

    def test_config_schema_version_matches_runtime_constant(self) -> None:
        config = (ROOT / "src/project_memory_kit/installer/templates/project-memory.config.yaml").read_text(
            encoding="utf-8"
        )
        match = re.search(r"^version:\s*(\d+)", config, re.M)
        self.assertIsNotNone(match)
        self.assertEqual(int(match.group(1)), CONFIG_SCHEMA_VERSION - 4)

    def test_readmes_mention_current_version(self) -> None:
        for name in ["README.md", "README.en.md", "CHANGELOG.md"]:
            self.assertIn(__version__, (ROOT / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
