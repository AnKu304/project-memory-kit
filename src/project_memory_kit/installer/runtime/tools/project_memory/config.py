from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


DEFAULT_CONFIG: dict[str, Any] = {
    "paths": {
        "graph_db": ".project-memory/graph.sqlite",
        "qdrant_path": ".project-memory/qdrant",
        "reports_dir": ".project-memory/reports",
        "logs_dir": ".project-memory/logs",
        "cache_dir": ".project-memory/cache",
    },
    "indexing": {
        "include_extensions": [".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json"],
        "ignore": [
            ".git/",
            ".project-memory/",
            "__pycache__/",
            ".venv/",
            "venv/",
            "node_modules/",
            "tools/project_memory/",
            "dist/",
            "build/",
            ".next/",
            ".cache/",
            "*.env",
            ".env*",
            "*.pem",
            "*.key",
            "*secret*",
            "*credential*",
        ],
    },
    "tests": {"default_commands": ["python -m unittest discover"], "test_roots": ["tests"]},
    "memory": {"max_context_chunks": 8, "vector_size": 64},
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(root: Path) -> dict[str, Any]:
    path = root / ".project-memory" / "config.yaml"
    if not path.exists() or yaml is None:
        return DEFAULT_CONFIG
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return deep_merge(DEFAULT_CONFIG, data)


def config_path(root: Path, key: str) -> Path:
    cfg = load_config(root)
    return root / cfg["paths"][key]
