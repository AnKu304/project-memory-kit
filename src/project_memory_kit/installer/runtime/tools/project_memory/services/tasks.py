from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tools.project_memory.services.index_project import index_project
from tools.project_memory.time_utils import utc_now


TASK_ROOT = ".agents/tasks"
CLOSED_STATUSES = {"done", "closed", "cancelled", "canceled"}
ROLE_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


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


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "task"


def _validate_role(role: str) -> str:
    clean = role.strip().lower() or "any"
    if not ROLE_RE.fullmatch(clean):
        raise ValueError("role must contain only letters, numbers, `_`, or `-`")
    return clean


def _insert_or_replace_field(text: str, name: str, value: str) -> str:
    if re.search(rf"(?im)^\s*{re.escape(name)}\s*:", text):
        return re.sub(rf"(?im)^(\s*{re.escape(name)}\s*:\s*).*$", rf"\g<1>{value}", text, count=1)
    lines = text.splitlines()
    insert_at = 1 if lines and lines[0].startswith("#") else 0
    lines.insert(insert_at, f"{name}: {value}")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _unique_task_path(root: Path, title: str) -> Path:
    task_root = root / TASK_ROOT
    task_root.mkdir(parents=True, exist_ok=True)
    base = _slug(title)
    path = task_root / f"{base}.md"
    counter = 2
    while path.exists():
        path = task_root / f"{base}-{counter}.md"
        counter += 1
    return path


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
    return _insert_or_replace_field(text, "Status", "done")


def create_task(
    root: Path,
    title: str,
    *,
    task_type: str = "handoff",
    role: str = "any",
    goal: str = "",
    context: str = "",
    evidence: list[str] | None = None,
    russian_subtitle: str = "",
) -> TaskItem:
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("title is required")
    clean_type = task_type.strip().lower() or "handoff"
    if clean_type not in {"user", "handoff"}:
        raise ValueError("task_type must be `user` or `handoff`")
    clean_role = _validate_role(role)
    heading = clean_title if not russian_subtitle.strip() else f"{clean_title} / {russian_subtitle.strip()}"
    evidence_lines = [f"- {item.strip()}" for item in evidence or [] if item.strip()] or ["- Not provided."]
    body = [
        f"# {heading}",
        "",
        f"Type: {clean_type}",
        "Status: active",
        f"Role: {clean_role}",
        "",
        "## Goal",
        "",
        goal.strip() or "Not provided.",
        "",
        "## Context",
        "",
        context.strip() or "Not provided.",
        "",
        "## Evidence",
        "",
        *evidence_lines,
        "",
        "## Done",
        "",
        "- [ ] Implementation or answer is complete.",
        "- [ ] Impact and tests were checked.",
        "- [ ] Knowledge/rationale was updated if durable context changed.",
    ]
    path = _unique_task_path(root, clean_title)
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    index_project(root, mode="changed")
    return next(item for item in list_tasks(root, include_closed=True) if item.path == path.relative_to(root).as_posix())


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


def assign_task(root: Path, file_path: str | Path, role: str, summary: str = "") -> TaskItem:
    path = _task_path(root, file_path)
    clean_role = _validate_role(role)
    text = path.read_text(encoding="utf-8", errors="replace")
    text = _insert_or_replace_field(text, "Role", clean_role).rstrip()
    assignment = [
        "",
        "## Assignment",
        "",
        f"- Assigned at: {utc_now()}",
        f"- Role: {clean_role}",
    ]
    if summary.strip():
        assignment.append(f"- Note: {summary.strip()}")
    path.write_text(text + "\n" + "\n".join(assignment) + "\n", encoding="utf-8")
    index_project(root, mode="changed")
    return next(item for item in list_tasks(root, include_closed=True) if item.path == path.relative_to(root).as_posix())


def format_tasks(tasks: list[TaskItem]) -> str:
    if not tasks:
        return "Tasks: none\n"
    lines = [f"Tasks: {len(tasks)}"]
    for item in tasks:
        lines.append(f"- [{item.status}] {item.role} {item.task_type}: {item.title} ({item.path})")
    return "\n".join(lines) + "\n"
