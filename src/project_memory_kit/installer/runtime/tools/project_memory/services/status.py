from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.project_memory.config import config_path, load_config
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.services.auto_index import index_freshness, index_locked, index_lock_path
from tools.project_memory.vector.qdrant_store import vector_backend_status


def project_status(root: Path) -> dict[str, Any]:
    cfg = load_config(root)
    freshness = index_freshness(root)
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    counts: dict[str, int] = {}
    with store.connect() as conn:
        for name, sql in {
            "nodes": "SELECT count(*) FROM nodes",
            "edges": "SELECT count(*) FROM edges",
            "chunks": "SELECT count(*) FROM chunks_fts",
            "indexed_files": "SELECT count(*) FROM file_index_state",
            "knowledge_current": "SELECT count(*) FROM knowledge_entries WHERE status = 'current'",
            "rationale_current": "SELECT count(*) FROM rationale_entries WHERE status = 'current'",
            "failures": "SELECT count(*) FROM failure_fingerprints",
        }.items():
            counts[name] = int(conn.execute(sql).fetchone()[0])

    return {
        "root": str(root),
        "index": {
            "fresh": freshness.fresh,
            "total_files": freshness.total_files,
            "indexed_files": freshness.indexed_files,
            "missing": freshness.missing_files,
            "stale": freshness.stale_files,
            "removed": freshness.removed_files,
            "sample": list(freshness.sample),
            "locked": index_locked(root),
            "lock_path": str(index_lock_path(root)),
        },
        "counts": counts,
        "vector": {
            "backend": cfg.get("vector", {}).get("backend", "auto"),
            "status": vector_backend_status(
                cfg.get("vector", {}).get("backend", "auto"),
                cfg.get("vector", {}).get("url"),
            ),
        },
        "search": cfg.get("search", {}),
        "parsers": cfg.get("parsers", {}),
        "modules": cfg.get("modules", {}),
    }


def format_status(report: dict[str, Any], fmt: str = "markdown") -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True)
    index = report["index"]
    counts = report["counts"]
    lines = [
        "Project Memory Status",
        f"- root: {report['root']}",
        (
            "- index: "
            f"fresh={index['fresh']} total={index['total_files']} indexed={index['indexed_files']} "
            f"missing={index['missing']} stale={index['stale']} removed={index['removed']} locked={index['locked']}"
        ),
        f"- vector: {report['vector']['status']}",
        f"- nodes: {counts['nodes']}",
        f"- edges: {counts['edges']}",
        f"- chunks: {counts['chunks']}",
        f"- current knowledge: {counts['knowledge_current']}",
        f"- current rationale: {counts['rationale_current']}",
        f"- failures: {counts['failures']}",
    ]
    if index["sample"]:
        lines.append("- sample:")
        lines.extend(f"  - {item}" for item in index["sample"])
    return "\n".join(lines) + "\n"


def format_stale(root: Path, fmt: str = "markdown") -> str:
    report = project_status(root)
    if fmt == "json":
        return json.dumps(report["index"], indent=2, sort_keys=True)
    index = report["index"]
    lines = [
        "Index Freshness",
        (
            f"- fresh={index['fresh']} missing={index['missing']} "
            f"stale={index['stale']} removed={index['removed']} locked={index['locked']}"
        ),
    ]
    if index["sample"]:
        lines.append("- sample:")
        lines.extend(f"  - {item}" for item in index["sample"])
    return "\n".join(lines) + "\n"
