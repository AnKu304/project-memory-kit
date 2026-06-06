from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from tools.project_memory.config import config_path, load_config
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.vector.qdrant_store import QdrantLocalStore


def _fts_query(query: str) -> str:
    terms = re.findall(r"[A-Za-zА-Яа-я0-9_]{2,}", query)
    return " ".join(terms[:12]) if terms else query.strip()


def _fts_search(store: SQLiteGraphStore, query: str, limit: int) -> list[dict[str, object]]:
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


def _rows_by_chunk_id(store: SQLiteGraphStore, chunk_ids: list[str]) -> dict[str, dict[str, object]]:
    if not chunk_ids:
        return {}
    placeholders = ",".join("?" for _ in chunk_ids)
    rows = store.query(
        f"""
        SELECT chunk_id, path, fqn, substr(content, 1, 240) AS snippet
        FROM chunks_fts
        WHERE chunk_id IN ({placeholders})
        """,
        tuple(chunk_ids),
    )
    return {str(row["chunk_id"]): dict(row) for row in rows}


def _vector_search(root: Path, store: SQLiteGraphStore, query: str, limit: int) -> list[dict[str, object]]:
    cfg = load_config(root)
    vector_cfg = cfg.get("vector", {})
    backend = vector_cfg.get("backend", "auto")
    if backend == "fallback":
        return []
    vectors = QdrantLocalStore(
        config_path(root, "qdrant_path"),
        cfg.get("memory", {}).get("vector_size", 64),
        backend=backend,
        collection=vector_cfg.get("collection", "project_memory_chunks"),
        model_name=vector_cfg.get("embedding_model"),
    )
    hits = vectors.search(query, limit)
    rows_by_id = _rows_by_chunk_id(store, [str(hit["chunk_id"]) for hit in hits])
    rows: list[dict[str, object]] = []
    for hit in hits:
        row = rows_by_id.get(str(hit["chunk_id"]))
        if row:
            row["score"] = hit["score"]
            row["source"] = "vector"
            rows.append(row)
    return rows


def search(root: Path, query: str, limit: int = 10) -> list[dict[str, object]]:
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    results: list[dict[str, object]] = []
    try:
        results.extend(_vector_search(root, store, query, limit))
    except RuntimeError:
        raise
    except Exception:
        results = []

    seen = {str(item["chunk_id"]) for item in results}
    for row in _fts_search(store, query, limit):
        if str(row["chunk_id"]) not in seen:
            results.append(row)
            seen.add(str(row["chunk_id"]))
        if len(results) >= limit:
            break
    return results[:limit]
