from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.project_memory.config import config_path
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore


def optimize_project(root: Path, vacuum: bool = False) -> dict[str, Any]:
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    with store.connect() as conn:
        before_page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        before_freelist = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        conn.execute("PRAGMA optimize")
        if vacuum:
            conn.execute("VACUUM")
        after_page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        after_freelist = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
    return {
        "db_path": str(config_path(root, "graph_db")),
        "vacuum": vacuum,
        "page_count_before": before_page_count,
        "page_count_after": after_page_count,
        "freelist_before": before_freelist,
        "freelist_after": after_freelist,
    }


def format_optimization(report: dict[str, Any], fmt: str = "markdown") -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True)
    return (
        "Memory Optimize\n"
        f"- db={report['db_path']}\n"
        f"- vacuum={report['vacuum']}\n"
        f"- page_count={report['page_count_before']} -> {report['page_count_after']}\n"
        f"- freelist={report['freelist_before']} -> {report['freelist_after']}\n"
    )
