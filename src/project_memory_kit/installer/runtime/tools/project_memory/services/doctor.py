from __future__ import annotations

import sqlite3
import json
from pathlib import Path

from tools.project_memory.config import config_path, load_config
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.services.migrations import migration_status
from tools.project_memory.version import __version__
from tools.project_memory.vector.qdrant_store import vector_backend_status


def doctor(root: Path) -> tuple[bool, str]:
    lines = ["Project memory doctor"]
    cfg = load_config(root)
    install_meta = _install_metadata(root)
    lines.append(f"- runtime version: {__version__}")
    if install_meta:
        lines.append(f"- installed version: {install_meta.get('runtime_version', 'unknown')}")
    lines.append(f"- config: {'ok' if cfg else 'missing'}")
    for key in ["graph_db", "qdrant_path", "reports_dir", "logs_dir"]:
        path = config_path(root, key)
        lines.append(f"- {key}: {path}")
    lines.append(f"- vector backend: {vector_backend_status(cfg.get('vector', {}).get('backend', 'auto'))}")
    try:
        store = SQLiteGraphStore(root, config_path(root, "graph_db"))
        store.initialize()
        with store.connect() as conn:
            conn.execute("SELECT count(*) FROM nodes").fetchone()
        current_migration, target_migration = migration_status(root)
        lines.append(f"- migrations: {current_migration}/{target_migration}")
        lines.append("- sqlite: ok")
        ok = True
    except sqlite3.Error as exc:
        lines.append(f"- sqlite: failed: {exc}")
        ok = False
    return ok, "\n".join(lines)


def _install_metadata(root: Path) -> dict[str, object]:
    path = root / ".project-memory" / "install.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
