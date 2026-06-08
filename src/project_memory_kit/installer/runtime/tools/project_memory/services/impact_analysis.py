from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.project_memory.config import config_path, load_config
from tools.project_memory.git_diff import changed_files, diff_ranges
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.services.auto_index import ensure_fresh_index

JS_TS_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"}


def _risk(changed_count: int, affected_count: int, test_count: int) -> str:
    if changed_count >= 8 or affected_count >= 12 or test_count == 0 and changed_count > 0:
        return "high"
    if changed_count >= 3 or affected_count >= 4:
        return "medium"
    return "low"


def _package_manager(root: Path) -> str:
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    if (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        return "bun"
    return "npm"


def _package_test_command(root: Path) -> str | None:
    package = root / "package.json"
    if not package.exists():
        return None
    try:
        data = json.loads(package.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None
    scripts = data.get("scripts", {})
    if not isinstance(scripts, dict):
        return None
    manager = _package_manager(root)
    test_script = str(scripts.get("test") or "")
    if test_script and "no test specified" not in test_script:
        return f"{manager} test"
    for script in ("test:unit", "vitest", "jest"):
        if script in scripts:
            return f"{manager} run {script}"
    return None


def _js_test_candidates(root: Path, changed_path: str) -> list[Path]:
    path = Path(changed_path)
    stem = path.stem
    suffix = path.suffix
    candidates = [
        path.with_name(f"{stem}.test{suffix}"),
        path.with_name(f"{stem}.spec{suffix}"),
        path.parent / "__tests__" / f"{stem}.test{suffix}",
        path.parent / "__tests__" / f"{stem}.spec{suffix}",
    ]
    return [candidate for candidate in candidates if (root / candidate).exists()]


def _default_test_commands(root: Path, changed: list[str]) -> list[tuple[str, str]]:
    if any(Path(path).suffix in JS_TS_SUFFIXES for path in changed):
        command = _package_test_command(root)
        if command:
            return [(command, "package.json test script for JS/TS changes")]
    commands = load_config(root).get("tests", {}).get("default_commands", ["python -m unittest discover"])
    return [(str(command), "configured default command") for command in commands]


def analyze_impact(root: Path, base: str = "HEAD") -> dict[str, Any]:
    ensure_fresh_index(root, "impact")
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    changed = changed_files(root, base)
    ranges = diff_ranges(root, base)
    touched_symbols: list[dict[str, Any]] = []
    affected_files: dict[str, str] = {}
    tests: dict[str, str] = {}

    for path in changed:
        affected_files[path] = "changed directly"
        for start, end in ranges.get(path, []):
            rows = store.query(
                """
                SELECT id, name, fqn, path, start_line, end_line
                FROM nodes
                WHERE kind = 'Symbol' AND path = ? AND start_line <= ? AND end_line >= ?
                """,
                (path, end, start),
            )
            for row in rows:
                item = dict(row)
                touched_symbols.append(item)
                callers = store.query(
                    """
                    SELECT src.path, src.fqn, e.kind, e.confidence, e.evidence
                    FROM edges e
                    JOIN nodes src ON src.id = e.src_id
                    WHERE e.dst_id = ? AND e.kind IN ('CALLS', 'REFERENCES', 'INHERITS')
                    """,
                    (row["id"],),
                )
                for caller in callers:
                    if caller["path"]:
                        affected_files[caller["path"]] = f"reverse {caller['kind']} from {caller['fqn']}"

        file_rows = store.query("SELECT id FROM nodes WHERE kind = 'File' AND path = ?", (path,))
        for file_row in file_rows:
            imports = store.query(
                """
                SELECT src.path, e.evidence
                FROM edges e
                JOIN nodes src ON src.id = e.src_id
                WHERE e.kind = 'IMPORTS' AND e.dst_id = ?
                """,
                (file_row["id"],),
            )
            for item in imports:
                if item["path"]:
                    affected_files[item["path"]] = f"reverse import via {item['evidence']}"

        if path.startswith("tests/") or Path(path).name.startswith("test_"):
            tests[path] = "changed test file"
        elif Path(path).suffix == ".py":
            candidate = Path("tests") / f"test_{Path(path).stem}.py"
            if (root / candidate).exists():
                tests[candidate.as_posix()] = f"path heuristic for {path}"
        elif Path(path).suffix in JS_TS_SUFFIXES:
            package_test = _package_test_command(root)
            for candidate in _js_test_candidates(root, path):
                if package_test:
                    tests[f"{package_test} -- {candidate.as_posix()}"] = f"path heuristic for {path}"
                else:
                    tests[candidate.as_posix()] = f"path heuristic for {path}"

    if changed and not tests:
        for command, reason in _default_test_commands(root, changed):
            tests[command] = reason

    return {
        "base": base,
        "changed_files": changed,
        "touched_symbols": touched_symbols,
        "affected_files": [{"path": path, "reason": reason} for path, reason in sorted(affected_files.items())],
        "tests": [{"target": target, "reason": reason} for target, reason in sorted(tests.items())],
        "risk": _risk(len(changed), len(affected_files), len(tests)),
    }


def format_impact(report: dict[str, Any], fmt: str = "markdown") -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True)
    lines = [
        "# Impact Report",
        "",
        f"Base: `{report['base']}`",
        f"Risk: **{report['risk']}**",
        "",
        "## Changed Files",
    ]
    if report["changed_files"]:
        lines.extend(f"- `{path}`" for path in report["changed_files"])
    else:
        lines.append("- No git diff changes detected.")
    lines.extend(["", "## Touched Symbols"])
    if report["touched_symbols"]:
        for item in report["touched_symbols"]:
            lines.append(f"- `{item['fqn']}` in `{item['path']}` lines {item['start_line']}-{item['end_line']}")
    else:
        lines.append("- No touched symbols found. Run `./pmem index --mode full` if this seems wrong.")
    lines.extend(["", "## Affected Files"])
    if report["affected_files"]:
        lines.extend(f"- `{item['path']}`: {item['reason']}" for item in report["affected_files"])
    else:
        lines.append("- No affected files found.")
    lines.extend(["", "## Tests"])
    if report["tests"]:
        lines.extend(f"- `{item['target']}`: {item['reason']}" for item in report["tests"])
    else:
        lines.append("- No targeted tests found.")
    return "\n".join(lines) + "\n"
