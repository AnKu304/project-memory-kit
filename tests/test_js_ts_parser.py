from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import sqlite3

RUNTIME = Path(__file__).resolve().parents[1] / "src/project_memory_kit/installer/runtime"
sys.path.insert(0, str(RUNTIME))

from tools.project_memory.parsers.js_ts import JsTsParser
from tools.project_memory.services.impact_analysis import analyze_impact, format_impact
from tools.project_memory.services.index_project import index_project


class JsTsParserTest(unittest.TestCase):
    def test_extracts_tsx_symbols_imports_and_jsx_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tsconfig.json").write_text(
                '{"compilerOptions":{"baseUrl":".","paths":{"@/*":["src/*"]}}}',
                encoding="utf-8",
            )
            components = root / "src" / "components"
            app = root / "src" / "app"
            components.mkdir(parents=True)
            app.mkdir(parents=True)
            button = components / "Button.tsx"
            button.write_text(
                "export function makeLabel(value: string) {\n"
                "  return value.toUpperCase();\n"
                "}\n\n"
                "export const Button = ({ label }: { label: string }) => {\n"
                "  return <button>{makeLabel(label)}</button>;\n"
                "};\n",
                encoding="utf-8",
            )
            page = app / "page.tsx"
            page.write_text(
                "import { Button, makeLabel as label } from '@/components/Button';\n\n"
                "export default function Page() {\n"
                "  return <Button label={label('home')} />;\n"
                "}\n",
                encoding="utf-8",
            )

            page_result = JsTsParser().parse(root, page)
            page_fqns = {symbol.fqn for symbol in page_result.symbols}
            page_symbol = next(symbol for symbol in page_result.symbols if symbol.name in {"Page", "default"})

            self.assertTrue({"src.app.page.Page", "src.app.page.default"} & page_fqns)
            self.assertIn("Button", page_symbol.references)
            self.assertEqual("src/components/Button.tsx", page_result.imports[0].target_path)

            button_result = JsTsParser().parse(root, button)
            button_fqns = {symbol.fqn for symbol in button_result.symbols}
            self.assertIn("src.components.Button.makeLabel", button_fqns)
            self.assertIn("src.components.Button.Button", button_fqns)

    def test_resolves_workspace_package_aliases_and_indexes_next_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".project-memory").mkdir()
            (root / ".project-memory/config.yaml").write_text("vector:\n  backend: fallback\n", encoding="utf-8")
            (root / "package.json").write_text(
                '{"workspaces":["packages/*"]}',
                encoding="utf-8",
            )
            ui = root / "packages" / "ui"
            ui_src = ui / "src"
            app = root / "apps" / "web" / "app" / "blog" / "[slug]"
            ui_src.mkdir(parents=True)
            app.mkdir(parents=True)
            (ui / "package.json").write_text(
                '{"name":"@acme/ui","exports":{".":"./src/index.ts","./button":"./src/button.tsx"}}',
                encoding="utf-8",
            )
            (ui_src / "button.tsx").write_text(
                "export function Button() {\n  return <button />;\n}\n",
                encoding="utf-8",
            )
            (ui_src / "index.ts").write_text("export { Button } from './button';\n", encoding="utf-8")
            page = app / "page.tsx"
            page.write_text(
                "import { Button } from '@acme/ui/button';\n"
                "export default function Page() {\n  return <Button />;\n}\n",
                encoding="utf-8",
            )

            result = JsTsParser().parse(root, page)
            self.assertEqual("packages/ui/src/button.tsx", result.imports[0].target_path)

            summary = index_project(root, mode="full")
            self.assertIn("indexed=", summary)
            conn = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                route = conn.execute(
                    "SELECT name, fqn, properties_json FROM nodes WHERE kind = 'Route'"
                ).fetchone()
            finally:
                conn.close()
            self.assertIsNotNone(route)
            self.assertEqual("/blog/[slug]", route[0])

    def test_indexes_next_route_components_boundaries_methods_and_impact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".project-memory").mkdir()
            (root / ".project-memory/config.yaml").write_text("vector:\n  backend: fallback\n", encoding="utf-8")
            (root / "tsconfig.json").write_text(
                '{"compilerOptions":{"baseUrl":".","paths":{"@/*":["src/*"]}}}',
                encoding="utf-8",
            )
            component_dir = root / "src" / "components"
            app_dir = root / "src" / "app"
            api_dir = app_dir / "api" / "submit"
            component_dir.mkdir(parents=True)
            api_dir.mkdir(parents=True)
            (component_dir / "Button.tsx").write_text(
                "export function Button() {\n  return <button />;\n}\n",
                encoding="utf-8",
            )
            page = app_dir / "page.tsx"
            page.write_text(
                "'use client';\n"
                "import { Button } from '@/components/Button';\n"
                "export default function Page() {\n  return <Button />;\n}\n",
                encoding="utf-8",
            )
            route = api_dir / "route.ts"
            route.write_text(
                "export async function GET() {\n  return Response.json({ ok: true });\n}\n"
                "export const POST = async () => Response.json({ ok: true });\n",
                encoding="utf-8",
            )

            subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            summary = index_project(root, mode="full")
            self.assertIn("route_bindings=", summary)
            conn = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                rows = conn.execute(
                    """
                    SELECT r.name, r.properties_json, dst.fqn, e.source
                    FROM edges e
                    JOIN nodes r ON r.id = e.src_id
                    JOIN nodes dst ON dst.id = e.dst_id
                    WHERE r.kind = 'Route' AND e.kind = 'ROUTE_COMPONENT'
                    ORDER BY r.name, dst.fqn
                    """
                ).fetchall()
            finally:
                conn.close()

            route_edges = [(row[0], json.loads(row[1]), row[2], row[3]) for row in rows]
            self.assertTrue(any(edge[0] == "/" and edge[2].endswith(".Page") for edge in route_edges))
            self.assertTrue(any(edge[0] == "/" and edge[2].endswith(".Button") for edge in route_edges))
            api_props = next(edge[1] for edge in route_edges if edge[0] == "/api/submit")
            self.assertEqual(api_props["route_kind"], "api_route")
            self.assertEqual(api_props["component_boundary"], "server")
            self.assertEqual(api_props["http_methods"], ["GET", "POST"])

            subprocess.run(
                ["git", "add", "src", "tsconfig.json"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            subprocess.run(
                ["git", "commit", "-m", "initial"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            page.write_text(
                "'use client';\n"
                "import { Button } from '@/components/Button';\n"
                "export default function Page() {\n  return <main><Button /></main>;\n}\n",
                encoding="utf-8",
            )

            impact = analyze_impact(root)
            rendered = format_impact(impact)
            self.assertIn("JS/TS Route Impact", rendered)
            self.assertIn("boundary=client", rendered)
            self.assertIn("`/` page_route", rendered)


if __name__ == "__main__":
    unittest.main()
