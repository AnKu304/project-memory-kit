from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.project_memory.config import config_path
from tools.project_memory.git_diff import changed_files, untracked_files, git_available, git_limitation
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.services.status import project_status
from tools.project_memory.services.tasks import list_tasks
from tools.project_memory.services.test_selector import select_tests


def local_evidence(root: Path, base: str = "HEAD") -> dict[str, Any]:
    status = project_status(root)
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    failures = store.query(
        """
        SELECT fingerprint, error_kind, normalized_message, last_seen_at, count, properties_json
        FROM failure_fingerprints
        ORDER BY last_seen_at DESC
        LIMIT 5
        """
    )
    failure_rows = []
    for row in failures:
        try:
            props = json.loads(row["properties_json"] or "{}")
        except json.JSONDecodeError:
            props = {}
        failure_rows.append(
            {
                "fingerprint": row["fingerprint"],
                "error_kind": row["error_kind"],
                "message": row["normalized_message"],
                "last_seen_at": row["last_seen_at"],
                "count": row["count"],
                "log_file": props.get("log_file"),
            }
        )
    active_tasks = list_tasks(root, include_closed=False)
    return {
        "base": base,
        "git_available": git_available(root),
        "diagnostics": [git_limitation(root)] if not git_available(root) else [],
        "changed_files": changed_files(root, base),
        "untracked_files": untracked_files(root),
        "index": status["index"],
        "tests": select_tests(root, base),
        "active_tasks": [item.__dict__ for item in active_tasks[:10]],
        "failures": failure_rows,
    }


def format_local_evidence(report: dict[str, Any]) -> str:
    index = report["index"]
    lines = [
        "Local Evidence",
        f"- base: {report['base']}",
        f"- changed_files: {len(report['changed_files']) if report.get('git_available', True) else 'unavailable'}",
        f"- untracked_files: {len(report['untracked_files']) if report.get('git_available', True) else 'unavailable'}",
        f"- index: fresh={index['fresh']} missing={index['missing']} stale={index['stale']}",
        f"- active_tasks: {len(report['active_tasks'])}",
        f"- tests: {len(report['tests'])}",
        f"- recent_failures: {len(report['failures'])}",
    ]
    lines.extend(f"- Warning: {item}" for item in report.get("diagnostics", []))
    if report["changed_files"]:
        lines.append("- changed sample:")
        lines.extend(f"  - {path}" for path in report["changed_files"][:8])
    if report["tests"]:
        lines.append("- test commands:")
        lines.extend(f"  - `{command}`" for command in report["tests"][:8])
    if report["failures"]:
        lines.append("- recent failure fingerprints:")
        for failure in report["failures"][:5]:
            lines.append(
                f"  - `{failure['fingerprint']}` {failure['error_kind']} "
                f"({failure['count']}x, last {failure['last_seen_at']})"
            )
    return "\n".join(lines) + "\n"
