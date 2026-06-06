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


def _fts_query_any(query: str) -> str:
    terms = re.findall(r"[A-Za-zА-Яа-я0-9_]{2,}", query)
    return " OR ".join(terms[:12]) if terms else query.strip()


def _fts_search(store: SQLiteGraphStore, query: str, limit: int, layer: str | None = None) -> list[dict[str, object]]:
    safe_query = _fts_query(query)
    layer_join = "JOIN nodes n ON n.id = chunks_fts.chunk_id" if layer else ""
    layer_where = "AND n.layer = ?" if layer else ""
    args: tuple[object, ...] = (safe_query, layer, limit) if layer else (safe_query, limit)
    try:
        rows = store.query(
            f"""
            SELECT chunks_fts.chunk_id, chunks_fts.path, chunks_fts.fqn, snippet(chunks_fts, 3, '[', ']', '...', 16) AS snippet
            FROM chunks_fts
            {layer_join}
            WHERE chunks_fts MATCH ?
            {layer_where}
            LIMIT ?
            """,
            args,
        )
        if not rows:
            any_query = _fts_query_any(query)
            if any_query != safe_query:
                args = (any_query, layer, limit) if layer else (any_query, limit)
                rows = store.query(
                    f"""
                    SELECT chunks_fts.chunk_id, chunks_fts.path, chunks_fts.fqn, snippet(chunks_fts, 3, '[', ']', '...', 16) AS snippet
                    FROM chunks_fts
                    {layer_join}
                    WHERE chunks_fts MATCH ?
                    {layer_where}
                    LIMIT ?
                    """,
                    args,
                )
    except sqlite3.Error:
        args = (f"%{query[:80]}%", layer, limit) if layer else (f"%{query[:80]}%", limit)
        rows = store.query(
            f"""
            SELECT chunks_fts.chunk_id, chunks_fts.path, chunks_fts.fqn, substr(content, 1, 240) AS snippet
            FROM chunks_fts
            {layer_join}
            WHERE content LIKE ?
            {layer_where}
            LIMIT ?
            """,
            args,
        )
    return [dict(row) for row in rows]


def _rows_by_chunk_id(store: SQLiteGraphStore, chunk_ids: list[str], layer: str | None = None) -> dict[str, dict[str, object]]:
    if not chunk_ids:
        return {}
    placeholders = ",".join("?" for _ in chunk_ids)
    layer_join = "JOIN nodes n ON n.id = chunks_fts.chunk_id" if layer else ""
    layer_where = "AND n.layer = ?" if layer else ""
    args: tuple[object, ...] = tuple(chunk_ids) + ((layer,) if layer else ())
    rows = store.query(
        f"""
        SELECT chunks_fts.chunk_id, chunks_fts.path, chunks_fts.fqn, substr(content, 1, 240) AS snippet
        FROM chunks_fts
        {layer_join}
        WHERE chunk_id IN ({placeholders})
        {layer_where}
        """,
        args,
    )
    return {str(row["chunk_id"]): dict(row) for row in rows}


def _vector_search(
    root: Path,
    store: SQLiteGraphStore,
    query: str,
    limit: int,
    layer: str | None = None,
) -> list[dict[str, object]]:
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
    rows_by_id = _rows_by_chunk_id(store, [str(hit["chunk_id"]) for hit in hits], layer=layer)
    rows: list[dict[str, object]] = []
    for hit in hits:
        row = rows_by_id.get(str(hit["chunk_id"]))
        if row:
            row["score"] = hit["score"]
            row["source"] = "vector"
            rows.append(row)
    return rows


def search(root: Path, query: str, limit: int = 10, layer: str | None = None) -> list[dict[str, object]]:
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    results: list[dict[str, object]] = []
    try:
        results.extend(_vector_search(root, store, query, limit, layer=layer))
    except RuntimeError:
        raise
    except Exception:
        results = []

    seen = {str(item["chunk_id"]) for item in results}
    for row in _fts_search(store, query, limit, layer=layer):
        if str(row["chunk_id"]) not in seen:
            results.append(row)
            seen.add(str(row["chunk_id"]))
        if len(results) >= limit:
            break
    return results[:limit]
