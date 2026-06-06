from __future__ import annotations

import json
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

    def test_mcp_stdio_lists_tools_and_calls_search(self) -> None:
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
            subprocess.run(
                [str(root / "pmem"), "index", "--mode", "full"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            messages = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "unittest", "version": "0"},
                    },
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "pmem_search",
                        "arguments": {"query": "pay amount", "limit": 5},
                    },
                },
            ]
            payload = "\n".join(json.dumps(message) for message in messages) + "\n"
            mcp = subprocess.run(
                [str(root / "pmem"), "mcp", "--root", str(root)],
                cwd=root,
                input=payload,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(mcp.returncode, 0, mcp.stderr)
            responses = [json.loads(line) for line in mcp.stdout.splitlines()]
            by_id = {item["id"]: item for item in responses}

            self.assertEqual(by_id[1]["result"]["protocolVersion"], "2025-06-18")
            tool_names = {tool["name"] for tool in by_id[2]["result"]["tools"]}
            self.assertIn("pmem_context", tool_names)
            self.assertIn("pmem_search", tool_names)
            self.assertIn("pmem_record_failure", tool_names)
            self.assertIn("app.py", by_id[3]["result"]["content"][0]["text"])
            self.assertIn("results", by_id[3]["result"]["structuredContent"])

    def test_knowledge_lifecycle_updates_current_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes = root / "notes"
            notes.mkdir()
            source = notes / "seo.md"
            source.write_text(
                "# Product Page SEO\n\nUse legacy-copy-token for product pages.\n",
                encoding="utf-8",
            )
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )

            add = subprocess.run(
                [
                    str(root / "pmem"),
                    "knowledge",
                    "add",
                    "--type",
                    "seo",
                    "--title",
                    "Product Page SEO",
                    "--file",
                    "notes/seo.md",
                    "--tags",
                    "seo,content",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(add.returncode, 0, add.stderr)
            self.assertIn("product-page-seo", add.stdout)
            self.assertTrue((root / ".project-memory/knowledge/seo/product-page-seo.md").exists())

            search = subprocess.run(
                [str(root / "pmem"), "knowledge", "search", "--query", "legacy-copy-token"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(search.returncode, 0, search.stderr)
            self.assertIn("Product Page SEO", search.stdout)

            source.write_text(
                "# Product Page SEO\n\nUse canonical-copy-token for product pages.\n",
                encoding="utf-8",
            )
            update = subprocess.run(
                [
                    str(root / "pmem"),
                    "knowledge",
                    "update",
                    "--id",
                    "product-page-seo",
                    "--file",
                    "notes/seo.md",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(update.returncode, 0, update.stderr)
            self.assertIn("v2", update.stdout)

            old_search = subprocess.run(
                [str(root / "pmem"), "knowledge", "search", "--query", "legacy-copy-token"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(old_search.returncode, 0, old_search.stderr)
            self.assertNotIn("legacy-copy-token", old_search.stdout)

            new_search = subprocess.run(
                [str(root / "pmem"), "search", "--query", "canonical-copy-token", "--layer", "knowledge"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(new_search.returncode, 0, new_search.stderr)
            self.assertIn("Product Page SEO", new_search.stdout)
            self.assertIn("canonical", new_search.stdout)

            context = subprocess.run(
                [
                    str(root / "pmem"),
                    "knowledge",
                    "context",
                    "--task",
                    "rewrite product page seo copy",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(context.returncode, 0, context.stderr)
            self.assertIn("## Current Knowledge", context.stdout)
            self.assertIn("product-page-seo", context.stdout)

            show = subprocess.run(
                [str(root / "pmem"), "knowledge", "show", "--id", "product-page-seo"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(show.returncode, 0, show.stderr)
            self.assertIn("version: 2", show.stdout)
            self.assertNotIn("version: 1", show.stdout)

            retire = subprocess.run(
                [str(root / "pmem"), "knowledge", "retire", "--id", "product-page-seo"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(retire.returncode, 0, retire.stderr)
            self.assertIn("archived", retire.stdout)

            retired_search = subprocess.run(
                [str(root / "pmem"), "knowledge", "search", "--query", "canonical-copy-token"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(retired_search.returncode, 0, retired_search.stderr)
            self.assertEqual(retired_search.stdout.strip(), "")

            conn = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                row = conn.execute(
                    "SELECT status, version FROM knowledge_entries WHERE id = 'product-page-seo'"
                ).fetchone()
            finally:
                conn.close()
            self.assertEqual(row, ("archived", 2))

    def test_rationale_lifecycle_and_reset_task_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes = root / "notes"
            notes.mkdir()
            source = notes / "storage.md"
            source.write_text(
                "# Storage Decision\n\nUse legacy-db-token as the source of truth.\n",
                encoding="utf-8",
            )
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )

            add = subprocess.run(
                [
                    str(root / "pmem"),
                    "rationale",
                    "add",
                    "--type",
                    "decision",
                    "--title",
                    "Storage Decision",
                    "--file",
                    "notes/storage.md",
                    "--why",
                    "local-first storage",
                    "--rejected",
                    "Remote database: unnecessary for local project memory",
                    "--evidence",
                    "doctor: sqlite ok",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(add.returncode, 0, add.stderr)
            self.assertIn("storage-decision", add.stdout)
            self.assertTrue((root / ".project-memory/rationale/decision/storage-decision.md").exists())

            search = subprocess.run(
                [str(root / "pmem"), "rationale", "search", "--query", "why remote database"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(search.returncode, 0, search.stderr)
            self.assertIn("Storage Decision", search.stdout)
            self.assertIn("0.", search.stdout)

            source.write_text(
                "# Storage Decision\n\nUse canonical-db-token as the source of truth.\n",
                encoding="utf-8",
            )
            update = subprocess.run(
                [
                    str(root / "pmem"),
                    "rationale",
                    "update",
                    "--id",
                    "storage-decision",
                    "--file",
                    "notes/storage.md",
                    "--why",
                    "SQLite is local-first and upgrade-safe",
                    "--evidence",
                    "tests: upgrade preserves graph.sqlite",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(update.returncode, 0, update.stderr)
            self.assertIn("v2", update.stdout)

            old_search = subprocess.run(
                [str(root / "pmem"), "rationale", "search", "--query", "legacy-db-token"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(old_search.returncode, 0, old_search.stderr)
            self.assertNotIn("legacy-db-token", old_search.stdout)

            layer_search = subprocess.run(
                [str(root / "pmem"), "search", "--query", "canonical db storage", "--layer", "rationale"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(layer_search.returncode, 0, layer_search.stderr)
            self.assertIn("rationale:storage-decision", layer_search.stdout)
            self.assertIn("matched", layer_search.stdout)

            context = subprocess.run(
                [
                    str(root / "pmem"),
                    "context",
                    "--task",
                    "change memory storage",
                    "--reset-task",
                    "--out",
                    ".project-memory/reports/CHANGE_CONTEXT.md",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(context.returncode, 0, context.stderr)
            report = (root / ".project-memory/reports/CHANGE_CONTEXT.md").read_text(encoding="utf-8")
            self.assertIn("## Task Boundary", report)
            self.assertIn("## Retrieved Rationale", report)
            self.assertIn("storage-decision", report)

            show = subprocess.run(
                [str(root / "pmem"), "rationale", "show", "--id", "storage-decision"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(show.returncode, 0, show.stderr)
            self.assertIn("version: 2", show.stdout)
            self.assertNotIn("version: 1", show.stdout)

            retire = subprocess.run(
                [str(root / "pmem"), "rationale", "retire", "--id", "storage-decision"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(retire.returncode, 0, retire.stderr)
            self.assertIn("archived", retire.stdout)

            retired_search = subprocess.run(
                [str(root / "pmem"), "rationale", "search", "--query", "canonical-db-token"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(retired_search.returncode, 0, retired_search.stderr)
            self.assertEqual(retired_search.stdout.strip(), "")

            conn = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                row = conn.execute(
                    "SELECT status, version FROM rationale_entries WHERE id = 'storage-decision'"
                ).fetchone()
            finally:
                conn.close()
            self.assertEqual(row, ("archived", 2))

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
