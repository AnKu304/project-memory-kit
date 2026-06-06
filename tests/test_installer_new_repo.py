from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from project_memory_kit.installer.install_project import install_project


class InstallerNewRepoTest(unittest.TestCase):
    def test_installs_memory_boilerplate_and_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text(
                "def greet(name):\n    return f'hello {name}'\n\nclass Greeter:\n    def run(self):\n        return greet('world')\n",
                encoding="utf-8",
            )
            install_project(root)

            self.assertTrue((root / "AGENTS.md").exists())
            self.assertTrue((root / ".agents/skills/dependency-graph-rag/SKILL.md").exists())
            self.assertTrue((root / ".project-memory/config.yaml").exists())
            self.assertTrue((root / "tools/project_memory/cli.py").exists())
            self.assertTrue((root / "pmem").exists())
            config_path = root / ".project-memory/config.yaml"
            config = config_path.read_text(encoding="utf-8")
            self.assertIn("backend: auto", config)
            agents = (root / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("This file is the project instruction hub", agents)
            self.assertIn("## Project Rules", agents)
            self.assertIn("## External Skills", agents)
            self.assertIn("PROJECT_RULES.md", agents)
            self.assertIn("<!-- PMEM:BEGIN -->", agents)

            doctor = subprocess.run([str(root / "pmem"), "doctor"], cwd=root, text=True, stdout=subprocess.PIPE)
            self.assertEqual(doctor.returncode, 0, doctor.stdout)
            self.assertIn("vector backend:", doctor.stdout)
            self.assertIn("sqlite: ok", doctor.stdout)

            config_path.write_text(config.replace("backend: auto", "backend: fallback"), encoding="utf-8")
            index = subprocess.run(
                [str(root / "pmem"), "index", "--mode", "full"], cwd=root, text=True, stdout=subprocess.PIPE
            )
            self.assertEqual(index.returncode, 0, index.stdout)
            self.assertIn("indexed=", index.stdout)


if __name__ == "__main__":
    unittest.main()
