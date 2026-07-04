from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.project_memory.config import config_path, load_config
from tools.project_memory.hashing import stable_id
from tools.project_memory.time_utils import utc_now


class MemoryBusyError(RuntimeError):
    pass


@dataclass(frozen=True)
class LockReport:
    exists: bool
    path: str
    stale: bool = False
    metadata: dict[str, Any] | None = None


def _settings(root: Path) -> dict[str, Any]:
    cfg = load_config(root)
    return cfg.get("concurrency", {})


def _write_lock_settings(root: Path) -> dict[str, Any]:
    return _settings(root).get("write_lock", {})


def _queue_settings(root: Path) -> dict[str, Any]:
    return _settings(root).get("queue", {})


def _runtime_dir(root: Path) -> Path:
    try:
        return config_path(root, "runtime_dir")
    except KeyError:
        return config_path(root, "cache_dir")


def write_lock_path(root: Path) -> Path:
    return _runtime_dir(root) / "write.lock"


def queue_dir(root: Path) -> Path:
    configured = str(_queue_settings(root).get("dir") or "").strip()
    return root / configured if configured else _runtime_dir(root) / "write-queue"


def _pid_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_metadata(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _lock_stale(path: Path, stale_seconds: float) -> bool:
    if not path.exists():
        return False
    metadata = _read_metadata(path)
    pid = metadata.get("pid")
    started = float(metadata.get("started_at_epoch") or 0)
    if isinstance(pid, int) and not _pid_running(pid):
        return True
    if started and stale_seconds > 0 and time.time() - started > stale_seconds:
        return True
    return not metadata and stale_seconds > 0 and time.time() - path.stat().st_mtime > stale_seconds


def _metadata(operation: str, kind: str = "write") -> dict[str, Any]:
    return {
        "kind": kind,
        "operation": operation,
        "pid": os.getpid(),
        "started_at": utc_now(),
        "started_at_epoch": time.time(),
        "cwd": str(Path.cwd()),
    }


class MemoryWriteLock:
    def __init__(self, root: Path, operation: str, timeout_seconds: float | None = None):
        self.root = root
        self.operation = operation
        settings = _write_lock_settings(root)
        self.enabled = bool(settings.get("enabled", True))
        env_timeout = os.environ.get("PMEM_WRITE_LOCK_TIMEOUT_SECONDS")
        default_timeout = env_timeout if env_timeout is not None else settings.get("timeout_seconds", 30)
        self.timeout = float(timeout_seconds if timeout_seconds is not None else default_timeout)
        self.stale_seconds = float(settings.get("stale_seconds", 900))
        self.path = write_lock_path(root)
        self.acquired = False

    def __enter__(self) -> "MemoryWriteLock":
        if not self.enabled or os.environ.get("PMEM_WRITE_LOCK_HELD") == "1":
            self.acquired = True
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + max(self.timeout, 0)
        while True:
            if _lock_stale(self.path, self.stale_seconds):
                self.path.unlink(missing_ok=True)
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if time.time() >= deadline:
                    raise MemoryBusyError(f"project memory write lock is busy: {self.path}")
                time.sleep(0.2)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(_metadata(self.operation), handle, indent=2, sort_keys=True)
                handle.write("\n")
            self.acquired = True
            return self

    def __exit__(self, *_: object) -> None:
        if self.acquired and self.enabled and os.environ.get("PMEM_WRITE_LOCK_HELD") != "1":
            self.path.unlink(missing_ok=True)


def lock_status(root: Path) -> list[LockReport]:
    stale_seconds = float(_write_lock_settings(root).get("stale_seconds", 900))
    paths = [write_lock_path(root), config_path(root, "cache_dir") / "index.lock"]
    reports: list[LockReport] = []
    for path in paths:
        reports.append(LockReport(path.exists(), str(path), _lock_stale(path, stale_seconds), _read_metadata(path)))
    return reports


def clear_locks(root: Path, stale_only: bool = True) -> list[str]:
    cleared: list[str] = []
    for report in lock_status(root):
        path = Path(report.path)
        if not path.exists() or (stale_only and not report.stale):
            continue
        path.unlink(missing_ok=True)
        cleared.append(str(path))
    return cleared


def enqueue_command(root: Path, argv: list[str], operation: str, reason: str) -> Path:
    qdir = queue_dir(root)
    qdir.mkdir(parents=True, exist_ok=True)
    item_id = stable_id("queue", str(time.time()), operation, " ".join(argv))[:16]
    path = qdir / f"{int(time.time())}-{item_id}.json"
    payload = {
        "id": path.stem,
        "operation": operation,
        "argv": argv,
        "reason": reason,
        "created_at": utc_now(),
        "cwd": str(root),
        "status": "pending",
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def queue_items(root: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    qdir = queue_dir(root)
    if not qdir.exists():
        return []
    for path in sorted(qdir.glob("*.json")):
        item = _read_metadata(path)
        item["path"] = str(path)
        items.append(item)
    return items


def clear_queue(root: Path, item_id: str | None = None) -> int:
    count = 0
    for item in queue_items(root):
        path = Path(str(item["path"]))
        if item_id and item.get("id") != item_id and path.stem != item_id:
            continue
        path.unlink(missing_ok=True)
        count += 1
    return count


def drain_queue(root: Path, limit: int | None = None) -> tuple[int, list[str]]:
    drained = 0
    errors: list[str] = []
    cli_path = Path(__file__).resolve().parents[1] / "cli.py"
    with MemoryWriteLock(root, "queue drain"):
        for item in queue_items(root)[: limit or None]:
            argv = [str(value) for value in item.get("argv") or []]
            env = {**os.environ, "PMEM_WRITE_LOCK_HELD": "1"}
            existing_path = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = str(root) + ((os.pathsep + existing_path) if existing_path else "")
            result = subprocess.run([sys.executable, str(cli_path), *argv], cwd=root, env=env, text=True)
            if result.returncode != 0:
                errors.append(f"{item.get('id')}: exit {result.returncode}")
                continue
            Path(str(item["path"])).unlink(missing_ok=True)
            drained += 1
    return drained, errors


def format_lock_status(reports: list[LockReport]) -> str:
    lines = ["Project memory locks"]
    for report in reports:
        state = "stale" if report.stale else "active" if report.exists else "free"
        operation = (report.metadata or {}).get("operation", "")
        suffix = f" operation={operation}" if operation else ""
        lines.append(f"- {report.path}: {state}{suffix}")
    return "\n".join(lines) + "\n"


def format_queue(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Queue: empty\n"
    lines = ["Queue:"]
    for item in items:
        lines.append(f"- {item.get('id')}: {item.get('operation')} {item.get('created_at')} {item.get('reason')}")
    return "\n".join(lines) + "\n"


def command_lock(args: argparse.Namespace) -> int:
    project_root = Path.cwd().resolve()
    if args.lock_command == "status":
        print(format_lock_status(lock_status(project_root)), end="")
        return 0
    if args.lock_command == "clear":
        cleared = clear_locks(project_root, stale_only=not args.force)
        print("cleared locks: " + (", ".join(cleared) if cleared else "none"))
        return 0
    return 2


def command_queue(args: argparse.Namespace) -> int:
    project_root = Path.cwd().resolve()
    if args.queue_command == "list":
        print(format_queue(queue_items(project_root)), end="")
        return 0
    if args.queue_command == "clear":
        print(f"cleared queue items: {clear_queue(project_root, args.id)}")
        return 0
    if args.queue_command == "drain":
        try:
            drained, errors = drain_queue(project_root, args.limit)
        except MemoryBusyError as exc:
            print(str(exc), file=sys.stderr)
            return 75
        print(f"drained queue items: {drained}")
        if errors:
            print("errors:")
            print("\n".join(f"- {item}" for item in errors))
            return 1
        return 0
    return 2


def _write_operation(args: argparse.Namespace) -> str | None:
    command = getattr(args, "command", "")
    if command in {"index", "record-failure", "migrate", "optimize", "watch"}:
        return command
    if command == "modules" and getattr(args, "modules_command", "") == "set":
        return "modules set"
    if command == "tasks" and getattr(args, "tasks_command", "") in {"close", "linear"}:
        return f"tasks {getattr(args, 'tasks_command')}"
    if command == "knowledge" and getattr(args, "knowledge_command", "") in {"add", "update", "retire"}:
        return f"knowledge {args.knowledge_command}"
    if command == "rationale" and getattr(args, "rationale_command", "") in {"add", "update", "retire"}:
        return f"rationale {args.rationale_command}"
    if command == "human" and getattr(args, "human_command", "") in {"export", "sync", "graph"}:
        return f"human {args.human_command}"
    return None


def _queue_enabled(root: Path) -> bool:
    return bool(_queue_settings(root).get("enabled", True))


def run_with_write_lock(root: Path, args: argparse.Namespace, argv: list[str], callback: Callable[[], int]) -> int:
    operation = _write_operation(args)
    if not operation:
        return callback()
    try:
        with MemoryWriteLock(root, operation):
            return callback()
    except MemoryBusyError as exc:
        if getattr(args, "command", "") == "queue" or not _queue_enabled(root):
            print(str(exc), file=sys.stderr)
            return 75
        queued = enqueue_command(root, argv, operation, str(exc))
        print(f"project memory busy; queued write: {queued}")
        print("Run `./pmem queue drain` after the current writer finishes.")
        return 0
