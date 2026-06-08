from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.project_memory.services.search import search
from tools.project_memory.services.status import project_status


def _load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        data = json.loads(line)
        if not isinstance(data, dict):
            raise ValueError(f"eval case must be an object at line {line_no}")
        data.setdefault("id", f"line-{line_no}")
        cases.append(data)
    return cases


def _case_passed(case: dict[str, Any], rows: list[dict[str, object]]) -> tuple[bool, str]:
    expect_path = case.get("expect_path")
    if expect_path and not any(str(row.get("path") or "") == str(expect_path) for row in rows):
        return False, f"expected path {expect_path}"
    expect_fqn = case.get("expect_fqn")
    if expect_fqn and not any(str(row.get("fqn") or "") == str(expect_fqn) for row in rows):
        return False, f"expected fqn {expect_fqn}"
    expect_text = case.get("expect_text")
    if expect_text and not any(str(expect_text) in str(row.get("snippet") or "") for row in rows):
        return False, f"expected text {expect_text}"
    return True, "matched"


def run_eval(root: Path, file_path: Path | None = None, limit: int = 10) -> dict[str, Any]:
    if file_path is None:
        status = project_status(root)
        passed = bool(status["index"]["fresh"])
        return {
            "total": 1,
            "passed": 1 if passed else 0,
            "failed": 0 if passed else 1,
            "cases": [
                {
                    "id": "builtin-index-fresh",
                    "passed": passed,
                    "reason": "index is fresh" if passed else "index is stale",
                }
            ],
        }

    cases = _load_cases(file_path)
    results: list[dict[str, Any]] = []
    for case in cases:
        query = str(case.get("query") or "").strip()
        if not query:
            raise ValueError(f"eval case {case.get('id')} is missing query")
        layer = case.get("layer")
        layer_arg = str(layer) if layer in {"knowledge", "rationale"} else None
        rows = search(root, query, limit=limit, layer=layer_arg)
        passed, reason = _case_passed(case, rows)
        results.append(
            {
                "id": case.get("id"),
                "query": query,
                "passed": passed,
                "reason": reason,
                "top_paths": [str(row.get("path") or "") for row in rows[:5]],
            }
        )
    passed_count = sum(1 for item in results if item["passed"])
    return {
        "total": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "cases": results,
    }


def format_eval(report: dict[str, Any], fmt: str = "markdown") -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True)
    lines = [
        "Project Memory Eval",
        f"- total={report['total']}",
        f"- passed={report['passed']}",
        f"- failed={report['failed']}",
    ]
    for case in report["cases"]:
        status = "pass" if case["passed"] else "fail"
        lines.append(f"- {status} {case['id']}: {case['reason']}")
    return "\n".join(lines) + "\n"
