from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.project_memory.config import config_path
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.services.knowledge import knowledge_conflict_count
from tools.project_memory.services.rationale import rationale_conflict_count
from tools.project_memory.services.secret_scan import scan_secrets
from tools.project_memory.services.status import project_status


def audit_project(root: Path, include_secrets: bool = False) -> dict[str, Any]:
    status = project_status(root)
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    issues: list[dict[str, Any]] = []
    index = status["index"]
    if not index["fresh"]:
        issues.append(
            {
                "kind": "stale_index",
                "severity": "warning",
                "detail": (
                    f"missing={index['missing']} stale={index['stale']} "
                    f"removed={index['removed']}"
                ),
            }
        )
    knowledge_conflicts = knowledge_conflict_count(root)
    if knowledge_conflicts:
        issues.append({"kind": "knowledge_conflict", "severity": "warning", "count": knowledge_conflicts})
    rationale_conflicts = rationale_conflict_count(root)
    if rationale_conflicts:
        issues.append({"kind": "rationale_conflict", "severity": "warning", "count": rationale_conflicts})

    rows = store.query(
        """
        SELECT id, title
        FROM rationale_entries
        WHERE status = 'current'
          AND (evidence_json IS NULL OR evidence_json = '[]')
        ORDER BY updated_at DESC
        LIMIT 20
        """
    )
    for row in rows:
        issues.append(
            {
                "kind": "rationale_without_evidence",
                "severity": "info",
                "id": row["id"],
                "title": row["title"],
            }
        )
    secret_findings = []
    if include_secrets:
        secret_findings = scan_secrets(root)
        for item in secret_findings:
            issues.append(
                {
                    "kind": "possible_secret",
                    "severity": "error",
                    "path": item.path,
                    "line": item.line,
                    "rule": item.rule,
                    "fingerprint": item.fingerprint,
                }
            )
    return {
        "ok": not any(item["severity"] == "error" for item in issues),
        "index_fresh": bool(index["fresh"]),
        "issues": issues,
        "secret_findings": [
            {
                "path": item.path,
                "line": item.line,
                "rule": item.rule,
                "fingerprint": item.fingerprint,
            }
            for item in secret_findings
        ],
        "status": status,
    }


def format_audit(report: dict[str, Any], fmt: str = "markdown") -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True)
    lines = [
        "Memory Audit",
        f"- ok={report['ok']}",
        f"- index_fresh={report['index_fresh']}",
        f"- issues={len(report['issues'])}",
    ]
    if report["issues"]:
        lines.append("- issue list:")
        for issue in report["issues"]:
            if issue.get("kind") == "possible_secret":
                detail = f"{issue.get('path')}:{issue.get('line')} {issue.get('rule')} {issue.get('fingerprint')}"
            else:
                detail = issue.get("detail") or issue.get("title") or issue.get("count") or ""
            lines.append(f"  - {issue['severity']} {issue['kind']}: {detail}")
    return "\n".join(lines) + "\n"
