from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


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


def format_tasks(tasks: list[TaskItem]) -> str:
    if not tasks:
        return "Tasks: none\n"
    lines = [f"Tasks: {len(tasks)}"]
    for item in tasks:
        lines.append(f"- [{item.status}] {item.role} {item.task_type}: {item.title} ({item.path})")
    return "\n".join(lines) + "\n"
