from __future__ import annotations

import fnmatch
from pathlib import Path

from tools.project_memory.config import load_config

SECRET_PATTERNS = [
    "*.env",
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*secret*",
    "*credential*",
    "*token*",
]


def is_binary(path: Path) -> bool:
    try:
        data = path.read_bytes()[:2048]
    except OSError:
        return True
    return b"\0" in data


def _patterns(root: Path) -> list[str]:
    cfg = load_config(root)
    patterns = list(cfg.get("indexing", {}).get("ignore", []))
    ignore_file = root / ".project-memoryignore"
    if ignore_file.exists():
        patterns.extend(
            line.strip()
            for line in ignore_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    patterns.extend(SECRET_PATTERNS)
    return patterns


def is_ignored(root: Path, path: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    parts = rel.split("/")
    if any(part in {".git", "__pycache__", "node_modules", ".venv", "venv"} for part in parts):
        return True
    for pattern in _patterns(root):
        normalized = pattern.strip()
        if not normalized:
            continue
        if normalized.endswith("/") and (rel.startswith(normalized) or normalized.rstrip("/") in parts):
            return True
        if fnmatch.fnmatch(rel, normalized) or fnmatch.fnmatch(path.name, normalized):
            return True
    return False


def should_index(root: Path, path: Path) -> bool:
    if not path.is_file() or is_ignored(root, path) or is_binary(path):
        return False
    cfg = load_config(root)
    include = set(cfg.get("indexing", {}).get("include_extensions", []))
    return path.suffix in include

