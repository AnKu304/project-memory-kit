from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.project_memory.config import config_path
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.services.knowledge import knowledge_conflict_count
from tools.project_memory.services.rationale import rationale_conflict_count


def _counts(store: SQLiteGraphStore, table: str) -> dict[str, int]:
    rows = store.query(f"SELECT status, count(*) AS count FROM {table} GROUP BY status ORDER BY status")
    return {str(row["status"]): int(row["count"]) for row in rows}


def _needs_review(store: SQLiteGraphStore) -> dict[str, int]:
    knowledge = store.query(
        """
        SELECT count(*) AS count
        FROM knowledge_entries
        WHERE status = 'current' AND (summary IS NULL OR trim(summary) = '')
        """
    )
    rationale = store.query(
        """
        SELECT evidence_json
        FROM rationale_entries
        WHERE status = 'current'
        """
    )
    rationale_count = 0
    for row in rationale:
        try:
            evidence = json.loads(row["evidence_json"] or "[]")
        except json.JSONDecodeError:
            evidence = []
        if not evidence:
            rationale_count += 1
    return {"knowledge": int(knowledge[0]["count"] if knowledge else 0), "rationale": rationale_count}


def lifecycle_report(root: Path) -> dict[str, Any]:
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    return {
        "knowledge": _counts(store, "knowledge_entries"),
        "rationale": _counts(store, "rationale_entries"),
        "conflicts": {
            "knowledge": knowledge_conflict_count(root),
            "rationale": rationale_conflict_count(root),
        },
        "needs_review": _needs_review(store),
    }


def format_lifecycle(report: dict[str, Any]) -> str:
    lines = ["Memory Lifecycle"]
    for layer in ["knowledge", "rationale"]:
        counts = report[layer]
        current = int(counts.get("current", 0))
        superseded = int(counts.get("superseded", 0))
        archived = int(counts.get("archived", 0))
        lines.append(f"- {layer}: current={current} superseded={superseded} archived={archived}")
    lines.append(
        "- conflicts: "
        f"knowledge={report['conflicts']['knowledge']} rationale={report['conflicts']['rationale']}"
    )
    lines.append(
        "- needs-review: "
        f"knowledge={report['needs_review']['knowledge']} rationale={report['needs_review']['rationale']}"
    )
    return "\n".join(lines) + "\n"
