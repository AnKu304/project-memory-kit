from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"

MAX_FUNCTION_LINES = 90
MAX_FILE_LINES = 600

ALLOWED_LONG_FUNCTIONS = {
    ("src/project_memory_kit/installer/runtime/tools/project_memory/cli.py", "build_parser"),
    ("src/project_memory_kit/installer/runtime/tools/project_memory/parsers/js_ts.py", "_parse_symbols"),
    ("src/project_memory_kit/installer/runtime/tools/project_memory/services/context_builder.py", "build_context"),
    ("src/project_memory_kit/installer/runtime/tools/project_memory/services/index_project.py", "_index_parse_result"),
    ("src/project_memory_kit/installer/runtime/tools/project_memory/services/rationale.py", "add_rationale"),
    ("src/project_memory_kit/installer/runtime/tools/project_memory/services/rationale.py", "update_rationale"),
}

ALLOWED_LARGE_FILES = {
    "src/project_memory_kit/installer/runtime/tools/project_memory/services/rationale.py": 720,
}


def _source_files() -> list[Path]:
    return [
        path
        for path in sorted(SOURCE_ROOT.rglob("*.py"))
        if "__pycache__" not in path.parts
    ]


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


class CodeBloatGuardTest(unittest.TestCase):
    def test_python_functions_stay_small_enough_to_review(self) -> None:
        failures: list[str] = []
        for path in _source_files():
            rel = _relative(path)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                lines = int(getattr(node, "end_lineno", node.lineno)) - int(node.lineno) + 1
                if lines <= MAX_FUNCTION_LINES or (rel, node.name) in ALLOWED_LONG_FUNCTIONS:
                    continue
                failures.append(f"{rel}:{node.lineno} {node.name} is {lines} lines")

        self.assertFalse(
            failures,
            "Split large functions or add a narrow allowlist entry with a reason:\n" + "\n".join(failures),
        )

    def test_python_files_do_not_grow_without_intentional_review(self) -> None:
        failures: list[str] = []
        for path in _source_files():
            rel = _relative(path)
            limit = ALLOWED_LARGE_FILES.get(rel, MAX_FILE_LINES)
            lines = len(path.read_text(encoding="utf-8").splitlines())
            if lines > limit:
                failures.append(f"{rel} is {lines} lines; limit is {limit}")

        self.assertFalse(
            failures,
            "Split large files or add a narrow allowlist entry with a reason:\n" + "\n".join(failures),
        )


if __name__ == "__main__":
    unittest.main()
