from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tools.project_memory.services.index_project import index_project
from tools.project_memory.time_utils import utc_now


TASK_ROOT = ".agents/tasks"
CLOSED_STATUSES = {"done", "closed", "cancelled", "canceled"}


@dataclass(frozen=True)
class TaskItem:
    path: str
    title: str
    status: str
    role: str
    task_type: str

    @property
    def active(self) -> bool:
        return self.status.lower() not in CLOSED_STATUSES


def _field(text: str, name: str, default: str = "") -> str:
    match = re.search(rf"(?im)^\s*{re.escape(name)}\s*:\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else default


def _title(text: str, path: Path) -> str:
    match = re.search(r"(?m)^#\s+(.+?)\s*$", text)
    return match.group(1).strip() if match else path.stem.replace("-", " ")


def list_tasks(root: Path, include_closed: bool = False, role: str | None = None) -> list[TaskItem]:
    task_root = root / TASK_ROOT
    if not task_root.exists():
        return []
    tasks: list[TaskItem] = []
    for path in sorted(task_root.rglob("*.md")):
        if "_templates" in path.parts or path.name.lower() == "readme.md":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        item = TaskItem(
            path=path.relative_to(root).as_posix(),
            title=_title(text, path),
            status=_field(text, "Status", "active").lower(),
            role=_field(text, "Role", "any").lower(),
            task_type=_field(text, "Type", "task").lower(),
        )
        if role and item.role not in {role.lower(), "any"}:
            continue
        if include_closed or item.active:
            tasks.append(item)
    return tasks


def _task_path(root: Path, file_path: str | Path) -> Path:
    path = Path(file_path)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    task_root = (root / TASK_ROOT).resolve()
    if task_root not in path.parents:
        raise ValueError(f"task file must be under {TASK_ROOT}")
    if "_templates" in path.parts or path.name.lower() == "readme.md":
        raise ValueError("cannot close task templates or README files")
    if not path.exists():
        raise FileNotFoundError(str(path))
    return path


def _set_status_done(text: str) -> str:
    if re.search(r"(?im)^\s*Status\s*:", text):
        return re.sub(r"(?im)^(\s*Status\s*:\s*).*$", r"\1done", text, count=1)
    lines = text.splitlines()
    insert_at = 1 if lines and lines[0].startswith("#") else 0
    lines.insert(insert_at, "Status: done")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def close_task(root: Path, file_path: str | Path, summary: str, command: str | None = None) -> TaskItem:
    path = _task_path(root, file_path)
    text = path.read_text(encoding="utf-8", errors="replace")
    text = _set_status_done(text).rstrip()
    lines = [
        "",
        "## Completion",
        "",
        f"- Completed at: {utc_now()}",
        f"- Summary: {summary.strip() or 'done'}",
    ]
    if command:
        lines.append(f"- Verified by: `{command.strip()}`")
    path.write_text(text + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    index_project(root, mode="changed")
    return next(
        item
        for item in list_tasks(root, include_closed=True)
        if item.path == path.relative_to(root).as_posix()
    )


def format_tasks(tasks: list[TaskItem]) -> str:
    if not tasks:
        return "Tasks: none\n"
    lines = [f"Tasks: {len(tasks)}"]
    for item in tasks:
        lines.append(f"- [{item.status}] {item.role} {item.task_type}: {item.title} ({item.path})")
    return "\n".join(lines) + "\n"
