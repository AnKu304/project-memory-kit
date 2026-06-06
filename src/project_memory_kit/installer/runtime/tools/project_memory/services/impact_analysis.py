from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.project_memory.config import config_path
from tools.project_memory.git_diff import changed_files, diff_ranges
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore


def _risk(changed_count: int, affected_count: int, test_count: int) -> str:
    if changed_count >= 8 or affected_count >= 12 or test_count == 0 and changed_count > 0:
        return "high"
    if changed_count >= 3 or affected_count >= 4:
        return "medium"
    return "low"


def analyze_impact(root: Path, base: str = "HEAD") -> dict[str, Any]:
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
        else:
            candidate = Path("tests") / f"test_{Path(path).stem}.py"
            if (root / candidate).exists():
                tests[candidate.as_posix()] = f"path heuristic for {path}"

    if changed and not tests:
        tests["python -m unittest discover"] = "fallback default command"

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

