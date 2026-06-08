from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
import sqlite3

RUNTIME = Path(__file__).resolve().parents[1] / "src/project_memory_kit/installer/runtime"
sys.path.insert(0, str(RUNTIME))

from tools.project_memory.parsers.js_ts import JsTsParser
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


if __name__ == "__main__":
    unittest.main()
