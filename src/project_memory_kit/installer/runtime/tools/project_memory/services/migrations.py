from __future__ import annotations

from pathlib import Path

from tools.project_memory.config import config_path
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.time_utils import utc_now
from tools.project_memory.version import GRAPH_SCHEMA_VERSION

MIGRATIONS: tuple[tuple[int, str], ...] = (
    (1, "initial_graph_schema"),
    (2, "knowledge_layer_schema"),
)


def apply_migrations(root: Path) -> list[str]:
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    applied: list[str] = []
    with store.connect() as conn:
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        existing = {int(row["version"]) for row in rows}
        for version, name in MIGRATIONS:
            if version in existing:
                continue
            conn.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                (version, name, utc_now()),
            )
            applied.append(f"{version}:{name}")
    return applied


def migration_status(root: Path) -> tuple[int, int]:
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    with store.connect() as conn:
        row = conn.execute("SELECT max(version) AS version FROM schema_migrations").fetchone()
    current = int(row["version"] or 0)
    return current, GRAPH_SCHEMA_VERSION
