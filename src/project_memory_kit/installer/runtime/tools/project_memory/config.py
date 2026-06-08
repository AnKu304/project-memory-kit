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
        "knowledge_dir": ".project-memory/knowledge",
        "rationale_dir": ".project-memory/rationale",
        "evals_dir": ".project-memory/evals",
        "human_dir": ".project-memory/human",
        "models_dir": ".project-memory/models",
    },
    "indexing": {
        "auto_index": {
            "enabled": True,
            "mode": "changed",
            "commands": ["search", "context", "impact", "tests", "watch"],
        },
        "include_extensions": [
            ".py",
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".mjs",
            ".cjs",
            ".mts",
            ".cts",
            ".md",
            ".txt",
            ".toml",
            ".yaml",
            ".yml",
            ".json",
        ],
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
    "search": {
        "weights": {
            "bm25": 0.35,
            "vector": 0.22,
            "term": 0.16,
            "path": 0.08,
            "graph": 0.07,
            "confidence": 0.06,
            "layer": 0.03,
            "recency": 0.03,
        }
    },
    "parsers": {
        "js_ts": {
            "backend": "auto",
            "fallback": "lexical",
            "optional_backends": ["typescript", "tree_sitter", "lsp", "lexical"],
        },
    },
    "memory": {"max_context_chunks": 8, "vector_size": 64},
    "knowledge": {"max_context_items": 5},
    "rationale": {"max_context_items": 5},
    "audit": {
        "secrets": {
            "max_file_bytes": 1_000_000,
            "max_findings": 100,
            "entropy_threshold": 4.2,
            "allowlist": [],
        },
    },
    "modules": {
        "human": {
            "enabled": False,
        },
    },
    "vector": {
        "backend": "auto",
        "collection": "project_memory_chunks",
        "embedding_model": None,
    },
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
