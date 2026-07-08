from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from tools.project_memory.config import config_path, load_config
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.services.auto_index import ensure_fresh_index
from tools.project_memory.vector.qdrant_store import QdrantLocalStore


def _terms(query: str) -> list[str]:
    return [term.lower() for term in re.findall(r"[A-Za-zА-Яа-я0-9_]{2,}", query)]


def _fts_query(query: str) -> str:
    terms = _terms(query)
    return " ".join(terms[:12]) if terms else query.strip()


def _fts_query_any(query: str) -> str:
    terms = _terms(query)
    return " OR ".join(terms[:12]) if terms else query.strip()


def _local_score(query: str, row: dict[str, object], source: str = "fts") -> tuple[float, str]:
    terms = _terms(query)
    haystack = " ".join(
        str(row.get(key) or "").lower()
        for key in ["path", "fqn", "snippet"]
    )
    matches = [term for term in terms if term in haystack]
    if not terms:
        return (0.1, source)
    coverage = len(set(matches)) / max(len(set(terms)), 1)
    path_bonus = 0.15 if any(term in str(row.get("path") or "").lower() for term in terms) else 0.0
    source_bonus = 0.25 if source == "vector" else 0.1
    score = min(1.0, source_bonus + coverage * 0.75 + path_bonus)
    reason = f"{source}; matched {len(set(matches))}/{len(set(terms))} query terms"
    return score, reason


def _term_coverage(query: str, row: dict[str, object]) -> float:
    terms = _terms(query)
    if not terms:
        return 0.0
    haystack = " ".join(str(row.get(key) or "").lower() for key in ["path", "fqn", "snippet"])
    matches = {term for term in terms if term in haystack}
    return len(matches) / max(len(set(terms)), 1)


def _path_score(query: str, row: dict[str, object]) -> float:
    terms = _terms(query)
    path = str(row.get("path") or "").lower()
    if not terms or not path:
        return 0.0
    return 1.0 if any(term in path for term in terms) else 0.0


def _annotate_rows(query: str, rows: list[dict[str, object]], source: str) -> list[dict[str, object]]:
    annotated: list[dict[str, object]] = []
    for row in rows:
        score, reason = _local_score(query, row, source=source)
        row["score"] = float(row.get("score") or score)
        row["source"] = source
        row["reason"] = reason
        annotated.append(row)
    return annotated


def _annotate_bm25_rows(query: str, rows: list[dict[str, object]]) -> list[dict[str, object]]:
    annotated: list[dict[str, object]] = []
    total = max(len(rows), 1)
    for index, row in enumerate(rows):
        local_score, local_reason = _local_score(query, row, source="bm25")
        order_score = max(0.05, 1.0 - (index / total) * 0.35)
        row["score"] = max(local_score, order_score)
        row["source"] = "bm25"
        row["components"] = {"bm25": row["score"], "term": _term_coverage(query, row), "path": _path_score(query, row)}
        row["reason"] = f"bm25 rank {float(row.get('bm25_rank') or 0.0):.6f}; {local_reason}"
        annotated.append(row)
    return annotated


def _layer_for_row(store: SQLiteGraphStore, row: dict[str, object]) -> str | None:
    rows = store.query("SELECT layer FROM nodes WHERE id = ?", (str(row.get("chunk_id") or ""),))
    if rows:
        return rows[0]["layer"]
    return None


def _graph_components(store: SQLiteGraphStore, chunk_id: str) -> tuple[float, float]:
    rows = store.query(
        """
        SELECT count(*) AS edge_count, avg(confidence) AS avg_confidence
        FROM edges
        WHERE src_id = ? OR dst_id = ?
        """,
        (chunk_id, chunk_id),
    )
    if not rows:
        return 0.0, 0.0
    edge_count = int(rows[0]["edge_count"] or 0)
    avg_confidence = float(rows[0]["avg_confidence"] or 0.0)
    return min(edge_count / 6.0, 1.0), max(0.0, min(avg_confidence, 1.0))


def _recency_component(store: SQLiteGraphStore, row: dict[str, object]) -> float:
    path = str(row.get("path") or "")
    if not path:
        return 0.0
    file_rows = store.query("SELECT indexed_at FROM file_index_state WHERE path = ?", (path,))
    if file_rows:
        return 0.7
    layer = _layer_for_row(store, row)
    if layer in {"knowledge", "rationale"}:
        return 0.8
    return 0.0


def _layer_component(layer: str | None) -> float:
    if layer in {"knowledge", "rationale"}:
        return 0.85
    if layer:
        return 0.65
    return 0.55


def _lifecycle_component(store: SQLiteGraphStore, row: dict[str, object]) -> tuple[float, str]:
    path = str(row.get("path") or "")
    if "/knowledge/" in path or path.startswith(".project-memory/knowledge/"):
        rows = store.query("SELECT status FROM knowledge_entries WHERE path = ?", (path,))
    elif "/rationale/" in path or path.startswith(".project-memory/rationale/"):
        rows = store.query("SELECT status FROM rationale_entries WHERE path = ?", (path,))
    else:
        return 1.0, "non-memory"
    if not rows:
        return 0.85, "memory record missing lifecycle row"
    status = str(rows[0]["status"])
    if status == "current":
        return 1.0, "current"
    if status == "superseded":
        return 0.35, "superseded"
    return 0.25, status


def _weights(root: Path) -> dict[str, float]:
    configured = load_config(root).get("search", {}).get("weights", {})
    defaults = {
        "bm25": 0.35,
        "vector": 0.22,
        "term": 0.16,
        "path": 0.08,
        "graph": 0.07,
        "confidence": 0.06,
        "layer": 0.03,
        "recency": 0.03,
    }
    for key, value in configured.items():
        if key in defaults:
            try:
                defaults[key] = float(value)
            except (TypeError, ValueError):
                pass
    return defaults


def _merge_candidates(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    for item in candidates:
        chunk_id = str(item.get("chunk_id") or "")
        if not chunk_id:
            continue
        existing = merged.get(chunk_id)
        if existing is None:
            copied = dict(item)
            copied["sources"] = [str(item.get("source") or "local")]
            copied["components"] = dict(item.get("components") or {})
            merged[chunk_id] = copied
            continue
        existing_sources = set(existing.get("sources") or [])
        existing_sources.add(str(item.get("source") or "local"))
        existing["sources"] = sorted(existing_sources)
        components = dict(existing.get("components") or {})
        for key, value in dict(item.get("components") or {}).items():
            components[key] = max(float(components.get(key) or 0.0), float(value or 0.0))
        existing["components"] = components
        if not existing.get("snippet") and item.get("snippet"):
            existing["snippet"] = item["snippet"]
    return list(merged.values())


def _apply_hybrid_scores(root: Path, store: SQLiteGraphStore, query: str, rows: list[dict[str, object]]) -> list[dict[str, object]]:
    weights = _weights(root)
    scored: list[dict[str, object]] = []
    for row in rows:
        chunk_id = str(row.get("chunk_id") or "")
        components: dict[str, float] = {key: float(value or 0.0) for key, value in dict(row.get("components") or {}).items()}
        components.setdefault("bm25", 0.0)
        components.setdefault("vector", 0.0)
        components["term"] = max(components.get("term", 0.0), _term_coverage(query, row))
        components["path"] = max(components.get("path", 0.0), _path_score(query, row))
        graph_score, confidence_score = _graph_components(store, chunk_id)
        components["graph"] = max(components.get("graph", 0.0), graph_score)
        components["confidence"] = max(components.get("confidence", 0.0), confidence_score)
        layer = _layer_for_row(store, row)
        components["layer"] = _layer_component(layer)
        components["recency"] = _recency_component(store, row)
        lifecycle, lifecycle_reason = _lifecycle_component(store, row)
        components["lifecycle"] = lifecycle
        score = min(1.0, sum(weights.get(key, 0.0) * value for key, value in components.items()))
        score *= lifecycle
        row["score"] = score
        row["source"] = "hybrid"
        row["components"] = {key: round(value, 4) for key, value in sorted(components.items())}
        row["reason"] = "hybrid rank from " + "+".join(str(item) for item in row.get("sources", ["local"]))
        if lifecycle != 1.0:
            row["reason"] += f"; lifecycle penalty: {lifecycle_reason}"
        scored.append(row)
    scored.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    return scored


def _snippet_key(item: dict[str, object]) -> str:
    snippet = re.sub(r"\s+", " ", str(item.get("snippet") or "").lower()).strip()
    return snippet[:180]


def _diversify_results(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    kept: list[dict[str, object]] = []
    seen_snippets: set[str] = set()
    path_counts: dict[str, int] = {}
    for row in rows:
        key = _snippet_key(row)
        if key and key in seen_snippets:
            continue
        path = str(row.get("path") or "")
        count = path_counts.get(path, 0)
        if count >= 2 and float(row.get("score") or 0.0) < 0.92:
            continue
        if count:
            row["score"] = float(row.get("score") or 0.0) * (0.9 ** count)
            row["reason"] = str(row.get("reason") or "matched") + f"; diversity penalty: same path #{count + 1}"
            components = dict(row.get("components") or {})
            components["diversity"] = round(0.9 ** count, 4)
            row["components"] = components
        path_counts[path] = count + 1
        if key:
            seen_snippets.add(key)
        kept.append(row)
    kept.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    return kept


def format_search_result(item: dict[str, Any], debug: bool = False) -> str:
    line = (
        f"{item['path']} {item['fqn']} "
        f"[{item.get('source', 'local')} {float(item.get('score') or 0.0):.2f}; {item.get('reason', 'matched')}]: "
        f"{item['snippet']}"
    )
    if debug:
        line += f" components={item.get('components', {})}"
    return line


def _fts_search(store: SQLiteGraphStore, query: str, limit: int, layer: str | None = None) -> list[dict[str, object]]:
    safe_query = _fts_query(query)
    layer_join = "JOIN nodes n ON n.id = chunks_fts.chunk_id" if layer else ""
    layer_where = "AND n.layer = ?" if layer else ""
    args: tuple[object, ...] = (safe_query, layer, limit) if layer else (safe_query, limit)
    used_bm25 = True
    try:
        rows = store.query(
            f"""
            SELECT chunks_fts.chunk_id, chunks_fts.path, chunks_fts.fqn,
                   snippet(chunks_fts, 3, '[', ']', '...', 16) AS snippet,
                   bm25(chunks_fts) AS bm25_rank
            FROM chunks_fts
            {layer_join}
            WHERE chunks_fts MATCH ?
            {layer_where}
            ORDER BY bm25_rank ASC
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
                    SELECT chunks_fts.chunk_id, chunks_fts.path, chunks_fts.fqn,
                           snippet(chunks_fts, 3, '[', ']', '...', 16) AS snippet,
                           bm25(chunks_fts) AS bm25_rank
                    FROM chunks_fts
                    {layer_join}
                    WHERE chunks_fts MATCH ?
                    {layer_where}
                    ORDER BY bm25_rank ASC
                    LIMIT ?
                    """,
                    args,
                )
    except sqlite3.Error:
        used_bm25 = False
        args = (f"%{query[:80]}%", layer, limit) if layer else (f"%{query[:80]}%", limit)
        rows = store.query(
            f"""
            SELECT chunks_fts.chunk_id, chunks_fts.path, chunks_fts.fqn,
                   substr(content, 1, 240) AS snippet
            FROM chunks_fts
            {layer_join}
            WHERE content LIKE ?
            {layer_where}
            LIMIT ?
            """,
            args,
        )
    dict_rows = [dict(row) for row in rows]
    if used_bm25:
        return _annotate_bm25_rows(query, dict_rows)
    return _annotate_rows(query, dict_rows, "like")


def _rows_by_chunk_id(store: SQLiteGraphStore, chunk_ids: list[str], layer: str | None = None) -> dict[str, dict[str, object]]:
    if not chunk_ids:
        return {}
    placeholders = ",".join("?" for _ in chunk_ids)
    layer_join = "JOIN nodes n ON n.id = chunks_fts.chunk_id" if layer else ""
    layer_where = "AND n.layer = ?" if layer else ""
    args: tuple[object, ...] = tuple(chunk_ids) + ((layer,) if layer else ())
    rows = store.query(
        f"""
        SELECT chunks_fts.chunk_id, chunks_fts.path, chunks_fts.fqn,
               substr(content, 1, 240) AS snippet
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
        url=vector_cfg.get("url"),
        root=root,
    )
    try:
        hits = vectors.search(query, limit)
    finally:
        vectors.close()
    rows_by_id = _rows_by_chunk_id(store, [str(hit["chunk_id"]) for hit in hits], layer=layer)
    rows: list[dict[str, object]] = []
    for hit in hits:
        row = rows_by_id.get(str(hit["chunk_id"]))
        if row:
            vector_score = float(hit["score"])
            local_score, reason = _local_score(query, row, source="local")
            row["score"] = max(vector_score, local_score)
            row["source"] = "vector"
            row["components"] = {"vector": max(0.0, min(vector_score, 1.0)), "term": _term_coverage(query, row), "path": _path_score(query, row)}
            row["reason"] = f"vector score plus {reason}"
            rows.append(row)
    return rows


def search(root: Path, query: str, limit: int = 10, layer: str | None = None, debug: bool = False) -> list[dict[str, object]]:
    ensure_fresh_index(root, "search")
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    candidates: list[dict[str, object]] = []
    try:
        candidates.extend(_vector_search(root, store, query, limit, layer=layer))
    except RuntimeError:
        raise
    except Exception:
        candidates = []

    for row in _fts_search(store, query, limit, layer=layer):
        candidates.append(row)
        if len(candidates) >= limit * 3:
            break
    results = _diversify_results(_apply_hybrid_scores(root, store, query, _merge_candidates(candidates)))
    if not debug:
        for item in results:
            item.pop("sources", None)
    return results[:limit]
