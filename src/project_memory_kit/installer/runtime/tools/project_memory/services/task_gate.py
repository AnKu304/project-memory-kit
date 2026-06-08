from __future__ import annotations

from typing import Any


def gate_report(evidence: dict[str, Any], impact: dict[str, Any], phase: str = "pre") -> dict[str, Any]:
    index = evidence["index"]
    active_tasks = evidence["active_tasks"]
    tests = evidence["tests"]
    checks = [
        {
            "name": "index_fresh",
            "ok": bool(index["fresh"]),
            "detail": "local index is fresh" if index["fresh"] else "run `./pmem index --mode changed`",
        },
        {
            "name": "active_tasks_checked",
            "ok": True,
            "detail": f"{len(active_tasks)} active task(s) visible",
        },
        {
            "name": "impact_available",
            "ok": True,
            "detail": f"risk={impact['risk']} changed={len(impact['changed_files'])}",
        },
        {
            "name": "tests_selected",
            "ok": bool(tests),
            "detail": "targeted or default tests selected" if tests else "no tests selected",
        },
    ]
    if phase == "post":
        checks.append(
            {
                "name": "close_or_update_task",
                "ok": True,
                "detail": "close related task and update knowledge/rationale only if durable context changed",
            }
        )
    return {"phase": phase, "ok": all(item["ok"] for item in checks), "checks": checks}


def format_gate(report: dict[str, Any]) -> str:
    lines = [f"Task Gate: {report['phase']}", f"- ok: {report['ok']}"]
    for item in report["checks"]:
        status = "pass" if item["ok"] else "warn"
        lines.append(f"- {status} {item['name']}: {item['detail']}")
    return "\n".join(lines) + "\n"
