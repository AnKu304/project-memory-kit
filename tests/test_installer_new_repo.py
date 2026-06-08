from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from project_memory_kit.installer.install_project import install_project
from project_memory_kit.version import __version__


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
            self.assertTrue((root / ".project-memory/install.json").exists())
            self.assertTrue((root / ".project-memory/knowledge").exists())
            self.assertTrue((root / ".project-memory/rationale").exists())
            self.assertTrue((root / "tools/project_memory/cli.py").exists())
            self.assertTrue((root / "tools/project_memory/mcp.py").exists())
            self.assertTrue((root / "pmem").exists())
            metadata = json.loads((root / ".project-memory/install.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["runtime_version"], __version__)
            config_path = root / ".project-memory/config.yaml"
            config = config_path.read_text(encoding="utf-8")
            self.assertIn("backend: auto", config)
            self.assertIn("knowledge_dir: .project-memory/knowledge", config)
            self.assertIn("rationale_dir: .project-memory/rationale", config)
            self.assertIn("human_dir: .project-memory/human", config)
            self.assertIn("human:", config)
            self.assertIn("enabled: false", config)
            self.assertFalse((root / ".project-memory/human").exists())
            agents = (root / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("This file is the project instruction hub", agents)
            self.assertIn("## Project Rules", agents)
            self.assertIn("## External Skills", agents)
            self.assertIn("PROJECT_RULES.md", agents)
            self.assertIn("<!-- PMEM:BEGIN -->", agents)

            doctor = subprocess.run([str(root / "pmem"), "doctor"], cwd=root, text=True, stdout=subprocess.PIPE)
            self.assertEqual(doctor.returncode, 0, doctor.stdout)
            self.assertIn(f"runtime version: {__version__}", doctor.stdout)
            self.assertIn("migrations: 3/3", doctor.stdout)
            self.assertIn("current knowledge entries:", doctor.stdout)
            self.assertIn("current rationale entries:", doctor.stdout)
            self.assertIn("possible knowledge conflicts:", doctor.stdout)
            self.assertIn("possible rationale conflicts:", doctor.stdout)
            self.assertIn("module human: disabled", doctor.stdout)
            self.assertIn("vector backend:", doctor.stdout)
            self.assertIn("sqlite: ok", doctor.stdout)

            version = subprocess.run([str(root / "pmem"), "version"], cwd=root, text=True, stdout=subprocess.PIPE)
            self.assertEqual(version.stdout.strip(), __version__)

            config_path.write_text(config.replace("backend: auto", "backend: fallback"), encoding="utf-8")
            index = subprocess.run(
                [str(root / "pmem"), "index", "--mode", "full"], cwd=root, text=True, stdout=subprocess.PIPE
            )
            self.assertEqual(index.returncode, 0, index.stdout)
            self.assertIn("indexed=", index.stdout)

    def test_upgrade_preserves_state_and_config_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("def saved():\n    return True\n", encoding="utf-8")
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )
            subprocess.run(
                [str(root / "pmem"), "index", "--mode", "full"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            knowledge_file = root / ".project-memory/knowledge/research/project.md"
            knowledge_file.parent.mkdir(parents=True)
            knowledge_file.write_text("# Project\n\nKeep this research note.\n", encoding="utf-8")
            rationale_file = root / ".project-memory/rationale/decision/storage.md"
            rationale_file.parent.mkdir(parents=True)
            rationale_file.write_text("# Storage\n\nKeep this rationale note.\n", encoding="utf-8")
            before = subprocess.run(
                [
                    "python3",
                    "-c",
                    "import sqlite3; c=sqlite3.connect('.project-memory/graph.sqlite'); print(c.execute(\"select count(*) from nodes\").fetchone()[0])",
                ],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            )
            install_project(root, upgrade=True)
            after = subprocess.run(
                [
                    "python3",
                    "-c",
                    "import sqlite3; c=sqlite3.connect('.project-memory/graph.sqlite'); print(c.execute(\"select count(*) from nodes\").fetchone()[0])",
                ],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(before.stdout.strip(), after.stdout.strip())
            self.assertIn("backend: fallback", config_path.read_text(encoding="utf-8"))
            self.assertTrue(knowledge_file.exists())
            self.assertTrue(rationale_file.exists())


if __name__ == "__main__":
    unittest.main()
