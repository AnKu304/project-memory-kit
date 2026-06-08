from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.project_memory.config import load_config
from tools.project_memory.services.index_project import index_project
from tools.project_memory.services.tasks import list_tasks
from tools.project_memory.time_utils import utc_now


@dataclass(frozen=True)
class LinearBridgeReport:
    path: str
    count: int
    enabled: bool = False


def _linear_config(root: Path) -> dict[str, Any]:
    cfg = load_config(root)
    linear = cfg.get("integrations", {}).get("linear", {})
    return linear if isinstance(linear, dict) else {}


def _bridge_dir(root: Path) -> Path:
    configured = str(_linear_config(root).get("bridge_dir") or ".project-memory/linear")
    path = Path(configured)
    return path if path.is_absolute() else root / path


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip().lower()).strip("-")
    return slug or "linear-task"


def linear_status(root: Path) -> dict[str, Any]:
    bridge = _bridge_dir(root)
    return {
        "enabled": bool(_linear_config(root).get("enabled", False)),
        "bridge_dir": str(bridge),
        "tasks": len(list_tasks(root, include_closed=True)),
        "exports": len(list(bridge.glob("*.json"))) if bridge.exists() else 0,
    }


def format_linear_status(status: dict[str, Any]) -> str:
    state = "enabled" if status["enabled"] else "disabled"
    return (
        "Linear bridge\n"
        f"- config: {state}\n"
        f"- bridge_dir: {status['bridge_dir']}\n"
        f"- local_tasks: {status['tasks']}\n"
        f"- bridge_files: {status['exports']}\n"
    )


def export_linear_tasks(root: Path, out: str | Path | None = None) -> LinearBridgeReport:
    bridge = _bridge_dir(root)
    bridge.mkdir(parents=True, exist_ok=True)
    path = Path(out) if out else bridge / "tasks-export.json"
    if not path.is_absolute():
        path = root / path
    tasks = list_tasks(root, include_closed=True)
    payload = {
        "schema": "pmem-linear-bridge-v1",
        "exported_at": utc_now(),
        "tasks": [
            {
                "title": task.title,
                "status": task.status,
                "role": task.role,
                "type": task.task_type,
                "path": task.path,
                "description": (root / task.path).read_text(encoding="utf-8", errors="replace"),
            }
            for task in tasks
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return LinearBridgeReport(str(path), len(tasks), bool(_linear_config(root).get("enabled", False)))


def _status_from_issue(issue: dict[str, Any]) -> str:
    raw = str(issue.get("status") or issue.get("state") or issue.get("state_name") or "active").lower()
    if raw in {"done", "completed", "closed", "canceled", "cancelled"}:
        return "done"
    return "active"


def _title_from_issue(issue: dict[str, Any]) -> str:
    return str(issue.get("title") or issue.get("name") or issue.get("identifier") or "Linear Task").strip()


def _issue_id(issue: dict[str, Any]) -> str:
    return str(issue.get("linear_id") or issue.get("identifier") or issue.get("id") or _title_from_issue(issue)).strip()


def _issue_description(issue: dict[str, Any]) -> str:
    return str(issue.get("description") or issue.get("body") or issue.get("summary") or "").strip()


def _task_path_for_issue(root: Path, issue: dict[str, Any]) -> Path:
    if issue.get("path"):
        candidate = root / str(issue["path"])
        task_root = (root / ".agents/tasks").resolve()
        resolved = candidate.resolve()
        if task_root in resolved.parents:
            return candidate
    linear_id = _issue_id(issue)
    title = _title_from_issue(issue)
    return root / ".agents/tasks/linear" / f"{_slug(linear_id)}-{_slug(title)[:48]}.md"


def _render_issue(issue: dict[str, Any]) -> str:
    title = _title_from_issue(issue)
    linear_id = _issue_id(issue)
    status = _status_from_issue(issue)
    role = str(issue.get("role") or "any").strip() or "any"
    issue_type = str(issue.get("type") or "linear").strip() or "linear"
    url = str(issue.get("url") or issue.get("linear_url") or "").strip()
    lines = [
        f"# {title}",
        "",
        f"Type: {issue_type}",
        f"Status: {status}",
        f"Role: {role}",
        f"Linear ID: {linear_id}",
    ]
    if url:
        lines.append(f"Linear URL: {url}")
    lines.extend(["", "## Description", "", _issue_description(issue), ""])
    return "\n".join(lines)


def import_linear_tasks(root: Path, file_path: str | Path) -> LinearBridgeReport:
    path = Path(file_path)
    if not path.is_absolute():
        path = root / path
    data = json.loads(path.read_text(encoding="utf-8"))
    issues = data.get("tasks") or data.get("issues") or []
    if not isinstance(issues, list):
        raise ValueError("Linear bridge file must contain a tasks or issues list")
    count = 0
    for raw in issues:
        if not isinstance(raw, dict):
            continue
        task_path = _task_path_for_issue(root, raw)
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text(_render_issue(raw), encoding="utf-8")
        count += 1
    if count:
        index_project(root, mode="changed")
    return LinearBridgeReport(str(path), count, bool(_linear_config(root).get("enabled", False)))


def format_linear_report(action: str, report: LinearBridgeReport) -> str:
    return f"Linear {action}\n- path: {report.path}\n- count: {report.count}\n"
