from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Iterable

from tools.project_memory.config import load_config
from tools.project_memory.git_diff import non_git_container

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
PRUNE_DIR_NAMES = {".git", ".project-memory", "__pycache__", "node_modules", ".venv", "venv"}
CONTAINER_EXCLUDES = {"agent", "archive", "archives", "raw", "backup", "backups", "logs", "screenshots", ".codex"}
DATABASE_PATTERNS = ("*.sqlite", "*.sqlite-*", "*.sqlite3", "*.sqlite3-*", "*.db", "*.db-*")


def confined_path(root: Path, path: Path | str) -> Path:
    root = root.absolute()
    candidate = Path(path)
    candidate = candidate if candidate.is_absolute() else root / candidate
    try:
        candidate.absolute().relative_to(root)
        candidate.resolve().relative_to(root.resolve())
    except (ValueError, OSError) as error:
        raise ValueError("Source path must stay inside the configured project root") from error
    return candidate


def is_sensitive_path(root: Path, path: Path) -> bool:
    parts = path.relative_to(root).parts
    return any(fnmatch.fnmatch(part, pattern) for part in parts for pattern in SECRET_PATTERNS)



def is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            data = handle.read(2048)
    except OSError:
        return True
    return b"\0" in data


def _patterns_from_config(root: Path, cfg: dict[str, object]) -> list[str]:
    indexing = cfg.get("indexing", {})
    configured = indexing.get("ignore", []) if isinstance(indexing, dict) else []
    patterns = list(configured)
    if non_git_container(root):
        patterns.extend(name + "/" for name in CONTAINER_EXCLUDES)
    ignore_file = root / ".project-memoryignore"
    if ignore_file.exists() and not ignore_file.is_symlink():
        patterns.extend(
            line.strip()
            for line in ignore_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    patterns.extend(SECRET_PATTERNS)
    return patterns


def _patterns(root: Path) -> list[str]:
    return _patterns_from_config(root, load_config(root))


def _ignored_rel(rel: str, name: str, parts: Iterable[str], patterns: list[str], ignore_file_patterns: bool = True) -> bool:
    part_list = list(parts)
    part_set = set(part_list)
    if PRUNE_DIR_NAMES.intersection(part_set) or any(fnmatch.fnmatch(name, pattern) for pattern in DATABASE_PATTERNS):
        return True
    for pattern in patterns:
        normalized = pattern.strip()
        if not normalized:
            continue
        if normalized.endswith("/") and (rel.startswith(normalized) or normalized.rstrip("/") in part_list):
            return True
        if not ignore_file_patterns:
            continue
        if fnmatch.fnmatch(rel, normalized) or fnmatch.fnmatch(name, normalized):
            return True
    return False


def is_ignored(root: Path, path: Path) -> bool:
    try:
        path = confined_path(root, path)
    except ValueError:
        return True
    rel = path.relative_to(root.absolute()).as_posix()
    return _ignored_rel(rel, path.name, rel.split("/"), _patterns(root))


def should_index(root: Path, path: Path) -> bool:
    try:
        path = confined_path(root, path)
    except ValueError:
        return False
    if is_ignored(root, path) or path.is_symlink() or not path.is_file() or is_binary(path):
        return False
    cfg = load_config(root)
    include = set(cfg.get("indexing", {}).get("include_extensions", []))
    return path.suffix in include


def iter_project_files(root: Path, ignore_file_patterns: bool = True) -> list[Path]:
    root = root.absolute()
    cfg = load_config(root)
    patterns = _patterns_from_config(root, cfg)
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        rel_dir = current.relative_to(root).as_posix() if current != root else ""
        kept_dirs: list[str] = []
        for dirname in dirnames:
            rel = f"{rel_dir}/{dirname}".strip("/")
            if not (current / dirname).is_symlink() and not _ignored_rel(rel, dirname, rel.split("/"), patterns, ignore_file_patterns):
                kept_dirs.append(dirname)
        dirnames[:] = kept_dirs
        for filename in filenames:
            path = current / filename
            rel = path.relative_to(root).as_posix()
            # Never open symlink targets while discovering project sources.
            if path.is_symlink() or _ignored_rel(rel, filename, rel.split("/"), patterns, ignore_file_patterns):
                continue
            if not ignore_file_patterns and is_sensitive_path(root, path):
                files.append(path)  # Audit may report this filename, never its content.
            elif not is_binary(path):
                files.append(path)
    return files


def iter_indexable_files(root: Path) -> list[Path]:
    cfg = load_config(root)
    include = set(cfg.get("indexing", {}).get("include_extensions", []))
    return [path for path in iter_project_files(root) if path.suffix in include]
