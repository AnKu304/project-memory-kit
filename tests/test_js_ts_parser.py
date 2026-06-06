from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[1] / "src/project_memory_kit/installer/runtime"
sys.path.insert(0, str(RUNTIME))

from tools.project_memory.parsers.js_ts import JsTsParser


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


if __name__ == "__main__":
    unittest.main()
