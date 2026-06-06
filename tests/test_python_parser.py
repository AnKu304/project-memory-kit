from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

RUNTIME = Path(__file__).resolve().parents[1] / "src/project_memory_kit/installer/runtime"
sys.path.insert(0, str(RUNTIME))
from tools.project_memory.parsers.python_ast import PythonAstParser


class PythonParserTest(unittest.TestCase):
    def test_extracts_classes_functions_methods_and_imports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = root / "pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            path = pkg / "mod.py"
            path.write_text(
                "import os\nfrom pkg import other\n\nclass Service(Base):\n    def run(self, x):\n        return helper(x)\n\ndef helper(value):\n    return value\n",
                encoding="utf-8",
            )
            result = PythonAstParser().parse(root, path)
            fqns = {symbol.fqn for symbol in result.symbols}
            self.assertIn("pkg.mod.Service", fqns)
            self.assertIn("pkg.mod.Service.run", fqns)
            self.assertIn("pkg.mod.helper", fqns)
            self.assertGreaterEqual(len(result.imports), 2)


if __name__ == "__main__":
    unittest.main()
