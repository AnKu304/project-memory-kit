from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from tools.project_memory.config import config_path
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore


def _fts_query(query: str) -> str:
    terms = re.findall(r"[A-Za-zА-Яа-я0-9_]{2,}", query)
    return " ".join(terms[:12]) if terms else query.strip()


def search(root: Path, query: str, limit: int = 10) -> list[dict[str, object]]:
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    safe_query = _fts_query(query)
    try:
        rows = store.query(
            """
            SELECT chunk_id, path, fqn, snippet(chunks_fts, 3, '[', ']', '...', 16) AS snippet
            FROM chunks_fts
            WHERE chunks_fts MATCH ?
            LIMIT ?
            """,
            (safe_query, limit),
        )
    except sqlite3.Error:
        rows = store.query(
            """
            SELECT chunk_id, path, fqn, substr(content, 1, 240) AS snippet
            FROM chunks_fts
            WHERE content LIKE ?
            LIMIT ?
            """,
            (f"%{query[:80]}%", limit),
        )
    return [dict(row) for row in rows]
