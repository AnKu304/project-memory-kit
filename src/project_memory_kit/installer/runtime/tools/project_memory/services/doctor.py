from __future__ import annotations

import sqlite3
from pathlib import Path

from tools.project_memory.config import config_path, load_config
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore


def doctor(root: Path) -> tuple[bool, str]:
    lines = ["Project memory doctor"]
    cfg = load_config(root)
    lines.append(f"- config: {'ok' if cfg else 'missing'}")
    for key in ["graph_db", "qdrant_path", "reports_dir", "logs_dir"]:
        path = config_path(root, key)
        lines.append(f"- {key}: {path}")
    try:
        store = SQLiteGraphStore(root, config_path(root, "graph_db"))
        store.initialize()
        with store.connect() as conn:
            conn.execute("SELECT count(*) FROM nodes").fetchone()
        lines.append("- sqlite: ok")
        ok = True
    except sqlite3.Error as exc:
        lines.append(f"- sqlite: failed: {exc}")
        ok = False
    return ok, "\n".join(lines)

