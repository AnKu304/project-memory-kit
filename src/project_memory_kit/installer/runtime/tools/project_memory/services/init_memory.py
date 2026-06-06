from __future__ import annotations

from pathlib import Path

from tools.project_memory.config import config_path
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore


def init_memory(root: Path) -> str:
    for name in ["reports_dir", "logs_dir", "cache_dir"]:
        config_path(root, name).mkdir(parents=True, exist_ok=True)
    config_path(root, "qdrant_path").mkdir(parents=True, exist_ok=True)
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    return f"initialized project memory at {root / '.project-memory'}"

