from __future__ import annotations

import subprocess
import sqlite3
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
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )

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

            search = subprocess.run(
                [str(root / "pmem"), "search", "--query", "pay amount", "--limit", "5"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(search.returncode, 0, search.stderr)
            self.assertIn("app.py", search.stdout)

    def test_indexes_js_ts_import_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            component_dir = root / "src" / "components"
            app_dir = root / "src" / "app"
            component_dir.mkdir(parents=True)
            app_dir.mkdir(parents=True)
            (root / "tsconfig.json").write_text(
                '{"compilerOptions":{"baseUrl":".","paths":{"@/*":["src/*"]}}}',
                encoding="utf-8",
            )
            (root / "package.json").write_text(
                '{"scripts":{"test":"vitest run"}}',
                encoding="utf-8",
            )
            (component_dir / "Button.tsx").write_text(
                "export const Button = ({ label }: { label: string }) => {\n"
                "  return <button>{label}</button>;\n"
                "};\n",
                encoding="utf-8",
            )
            (app_dir / "page.tsx").write_text(
                "import { Button } from '@/components/Button';\n\n"
                "export default function Page() {\n"
                "  return <Button label=\"Home\" />;\n"
                "}\n",
                encoding="utf-8",
            )
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )

            index = subprocess.run(
                [str(root / "pmem"), "index", "--mode", "full"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertIn("indexed=", index.stdout)

            conn = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                symbol_count = conn.execute(
                    "SELECT count(*) FROM nodes WHERE kind = 'Symbol' AND language = 'typescript'"
                ).fetchone()[0]
                imports = conn.execute(
                    """
                    SELECT dst.path
                    FROM edges e
                    JOIN nodes src ON src.id = e.src_id
                    JOIN nodes dst ON dst.id = e.dst_id
                    WHERE e.kind = 'IMPORTS' AND src.path = 'src/app/page.tsx'
                    """
                ).fetchall()
            finally:
                conn.close()

            self.assertGreaterEqual(symbol_count, 2)
            self.assertIn(("src/components/Button.tsx",), imports)

            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            subprocess.run(["git", "add", "src", "tsconfig.json", "package.json"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            button_path = component_dir / "Button.tsx"
            button_path.write_text(button_path.read_text(encoding="utf-8").replace("{label}", "{label.toUpperCase()}"), encoding="utf-8")

            impact = subprocess.run(
                [str(root / "pmem"), "impact", "--base", "HEAD", "--format", "markdown"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertIn("reverse import via @/components/Button", impact.stdout)
            self.assertIn("npm test", impact.stdout)

    def test_binds_js_ts_named_imports_through_barrel_exports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            component_dir = root / "src" / "components"
            app_dir = root / "src" / "app"
            component_dir.mkdir(parents=True)
            app_dir.mkdir(parents=True)
            (root / "tsconfig.json").write_text(
                '{"compilerOptions":{"baseUrl":".","paths":{"@/*":["src/*"]}}}',
                encoding="utf-8",
            )
            (component_dir / "Button.tsx").write_text(
                "export const Button = ({ label }: { label: string }) => {\n"
                "  return <button>{label}</button>;\n"
                "};\n",
                encoding="utf-8",
            )
            (component_dir / "index.ts").write_text(
                "export { Button } from './Button';\n",
                encoding="utf-8",
            )
            (app_dir / "page.tsx").write_text(
                "import { Button } from '@/components';\n\n"
                "export default function Page() {\n"
                "  return <Button label=\"Home\" />;\n"
                "}\n",
                encoding="utf-8",
            )
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

            conn = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                rows = conn.execute(
                    """
                    SELECT src.fqn, dst.fqn, e.kind, e.confidence
                    FROM edges e
                    JOIN nodes src ON src.id = e.src_id
                    JOIN nodes dst ON dst.id = e.dst_id
                    WHERE e.source = 'binding'
                      AND src.fqn = 'src.app.page.Page'
                      AND dst.fqn = 'src.components.Button.Button'
                    ORDER BY e.kind
                    """
                ).fetchall()
            finally:
                conn.close()

            kinds = {row[2] for row in rows}
            self.assertIn("REFERENCES", kinds)
            self.assertIn("CALLS", kinds)
            self.assertTrue(all(row[3] > 0.7 for row in rows))


if __name__ == "__main__":
    unittest.main()
