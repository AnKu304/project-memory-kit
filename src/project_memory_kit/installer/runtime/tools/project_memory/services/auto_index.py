from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from tools.project_memory.config import config_path, load_config
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.hashing import sha256_file
from tools.project_memory.ignore import should_index


@dataclass(frozen=True)
class IndexFreshness:
    total_files: int
    indexed_files: int
    missing_files: int
    stale_files: int
    removed_files: int
    sample: tuple[str, ...]

    @property
    def fresh(self) -> bool:
        return (
            self.total_files == self.indexed_files
            and self.missing_files == 0
            and self.stale_files == 0
            and self.removed_files == 0
        )


def iter_indexable_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if should_index(root, path)]


def index_freshness(root: Path, sample_limit: int = 8) -> IndexFreshness:
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    files = iter_indexable_files(root)
    sample: list[str] = []
    missing = 0
    stale = 0
    indexed = 0
    current_paths: set[str] = set()

    for path in files:
        rel = path.relative_to(root).as_posix()
        current_paths.add(rel)
        current_hash = sha256_file(path)
        stored_hash = store.file_hash(rel)
        if stored_hash is None:
            missing += 1
            if len(sample) < sample_limit:
                sample.append(rel)
            continue
        indexed += 1
        if stored_hash != current_hash:
            stale += 1
            if len(sample) < sample_limit:
                sample.append(rel)

    removed_paths = sorted(store.indexed_file_paths() - current_paths)
    for rel in removed_paths[: max(sample_limit - len(sample), 0)]:
        sample.append(rel)

    return IndexFreshness(
        total_files=len(files),
        indexed_files=indexed,
        missing_files=missing,
        stale_files=stale,
        removed_files=len(removed_paths),
        sample=tuple(sample),
    )


def auto_index_enabled(root: Path, command: str) -> bool:
    cfg = load_config(root)
    auto_cfg = cfg.get("indexing", {}).get("auto_index", {})
    if not bool(auto_cfg.get("enabled", True)):
        return False
    commands = auto_cfg.get("commands", ["search", "context", "impact", "tests"])
    return command in {str(item) for item in commands}


def index_lock_path(root: Path) -> Path:
    return config_path(root, "cache_dir") / "index.lock"


def index_locked(root: Path) -> bool:
    return index_lock_path(root).exists()


class IndexLock:
    def __init__(self, root: Path):
        self.path = index_lock_path(root)
        self.acquired = False

    def __enter__(self) -> "IndexLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return self
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        self.acquired = True
        return self

    def __exit__(self, *_: object) -> None:
        if self.acquired:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


def ensure_fresh_index(root: Path, command: str) -> str | None:
    if not auto_index_enabled(root, command):
        return None
    freshness = index_freshness(root)
    if freshness.fresh:
        return None

    cfg = load_config(root)
    mode = str(cfg.get("indexing", {}).get("auto_index", {}).get("mode") or "changed")
    if mode not in {"changed", "full"}:
        mode = "changed"

    with IndexLock(root) as lock:
        if not lock.acquired:
            return f"auto-index before {command}: skipped because index.lock exists"

        from tools.project_memory.services.index_project import index_project

        report = index_project(root, mode=mode)
    sample = ", ".join(freshness.sample)
    reason = (
        f"auto-index before {command}: missing={freshness.missing_files} "
        f"stale={freshness.stale_files} removed={freshness.removed_files}"
    )
    if sample:
        reason += f" sample={sample}"
    return f"{reason}\n{report}"
