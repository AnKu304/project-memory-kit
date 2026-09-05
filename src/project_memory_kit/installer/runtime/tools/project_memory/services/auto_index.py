from __future__ import annotations

import os
import json
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path

from tools.project_memory.config import config_path, load_config
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.hashing import sha256_file
from tools.project_memory.ignore import iter_indexable_files
from tools.project_memory.services.concurrency import MemoryBusyError, MemoryWriteLock, _lock_stale, _metadata


@dataclass
class _ReadRequest:
    fresh: set[str] = field(default_factory=set)
    vector_busy: set[str] = field(default_factory=set)
    notices: dict[str, list[str]] = field(default_factory=dict)
    resources: dict[tuple, object] = field(default_factory=dict)


_read_request: ContextVar[_ReadRequest | None] = ContextVar("pmem_read_request", default=None)


def note_request_diagnostic(root: Path, message: str) -> None:
    state = _read_request.get()
    if state is not None:
        notices = state.notices.setdefault(str(root.resolve()), [])
        if message not in notices:
            notices.append(message)


def request_freshness_diagnostics(root: Path) -> list[str]:
    state = _read_request.get()
    return list(state.notices.get(str(root.resolve()), [])) if state is not None else []


def request_vector_busy(root: Path) -> bool:
    state = _read_request.get()
    return state is not None and str(root.resolve()) in state.vector_busy


def mark_request_vector_busy(root: Path, message: str) -> None:
    state = _read_request.get()
    if state is not None:
        state.vector_busy.add(str(root.resolve()))
        note_request_diagnostic(root, message)


def request_resource(root: Path, key: tuple, factory):
    """At most eight resources, shared only by one context assembly/root/model.

    Used for embedders and query vectors, never clients holding database locks.
    Failed construction is not cached. No resource outlives this read request.
    """
    state = _read_request.get()
    cache_key = (str(root.resolve()), *key)
    if state is None:
        return factory()
    if cache_key in state.resources:
        return state.resources[cache_key]
    value = factory()
    if len(state.resources) < 8:
        state.resources[cache_key] = value
    return value


def reuse_request_freshness(function):
    """Reuse successful checks only within one read-only context assembly.

    This is not a background cache or a transaction snapshot. Each invocation,
    including the next MCP call, starts fresh and releases its state on errors.
    """
    @wraps(function)
    def wrapped(*args, **kwargs):
        token = _read_request.set(_ReadRequest())
        try:
            result = function(*args, **kwargs)
            if isinstance(result, str):
                root = args[0] if args else kwargs['root']
                notices = request_freshness_diagnostics(root)
                if notices:
                    result += '\n## Memory Availability\n' + '\n'.join(f'- {notice}' for notice in notices) + '\n'
            return result
        finally:
            _read_request.reset(token)
    return wrapped


def _remember_fresh(root: Path) -> None:
    state = _read_request.get()
    if state is not None:
        state.fresh.add(str(root.resolve()))


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


def index_freshness(root: Path, sample_limit: int = 8) -> IndexFreshness:
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    files = iter_indexable_files(root)
    stored_hashes = store.indexed_file_hashes()
    sample: list[str] = []
    missing = 0
    stale = 0
    indexed = 0
    current_paths: set[str] = set()

    for path in files:
        rel = path.relative_to(root).as_posix()
        current_paths.add(rel)
        current_hash = sha256_file(path)
        stored_hash = stored_hashes.get(rel)
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

    removed_paths = sorted(stored_hashes.keys() - current_paths)
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
    path = index_lock_path(root)
    stale_seconds = float(load_config(root).get("concurrency", {}).get("write_lock", {}).get("stale_seconds", 900))
    if _lock_stale(path, stale_seconds):
        path.unlink(missing_ok=True)
        return False
    return path.exists()


class IndexLock:
    def __init__(self, root: Path):
        self.root = root
        self.path = index_lock_path(root)
        self.acquired = False

    def __enter__(self) -> "IndexLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stale_seconds = float(load_config(self.root).get("concurrency", {}).get("write_lock", {}).get("stale_seconds", 900))
        if _lock_stale(self.path, stale_seconds):
            self.path.unlink(missing_ok=True)
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return self
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(_metadata("auto-index", kind="index"), handle, indent=2, sort_keys=True)
            handle.write("\n")
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
    state = _read_request.get()
    if state is not None and str(root.resolve()) in state.fresh:
        return None
    if request_vector_busy(root):
        return 'Auto-index skipped: local Qdrant is busy; existing results may be stale.'
    freshness = index_freshness(root)
    if freshness.fresh:
        _remember_fresh(root)
        return None

    cfg = load_config(root)
    mode = str(cfg.get("indexing", {}).get("auto_index", {}).get("mode") or "changed")
    if mode not in {"changed", "full"}:
        mode = "changed"

    from tools.project_memory.vector.qdrant_store import VectorBackendBusyError
    try:
        with MemoryWriteLock(root, f"auto-index before {command}", timeout_seconds=0):
            with IndexLock(root) as lock:
                if not lock.acquired:
                    return f"auto-index before {command}: skipped because index.lock exists"

                from tools.project_memory.services.index_project import index_project

                report = index_project(root, mode=mode)
    except VectorBackendBusyError:
        if state is None:
            raise
        notice = 'Auto-index unavailable: local Qdrant is busy; existing lexical/graph results may be stale.'
        mark_request_vector_busy(root, notice)
        return notice
    except MemoryBusyError:
        notice = f"auto-index before {command}: skipped because write.lock exists; existing results may be stale"
        note_request_diagnostic(root, notice)
        return notice
    _remember_fresh(root)
    sample = ", ".join(freshness.sample)
    reason = (
        f"auto-index before {command}: missing={freshness.missing_files} "
        f"stale={freshness.stale_files} removed={freshness.removed_files}"
    )
    if sample:
        reason += f" sample={sample}"
    return f"{reason}\n{report}"
