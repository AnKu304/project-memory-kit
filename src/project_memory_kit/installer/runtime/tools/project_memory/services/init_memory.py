from __future__ import annotations

from pathlib import Path

from tools.project_memory.config import config_path
from tools.project_memory.services.migrations import apply_migrations
from tools.project_memory.services.modules import ensure_enabled_module_paths


def init_memory(root: Path) -> str:
    for name in ["reports_dir", "logs_dir", "cache_dir", "knowledge_dir", "rationale_dir", "evals_dir"]:
        config_path(root, name).mkdir(parents=True, exist_ok=True)
    config_path(root, "qdrant_path").mkdir(parents=True, exist_ok=True)
    ensure_enabled_module_paths(root)
    apply_migrations(root)
    return f"initialized project memory at {root / '.project-memory'}"
