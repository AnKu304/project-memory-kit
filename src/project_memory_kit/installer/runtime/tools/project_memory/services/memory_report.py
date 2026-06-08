from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.project_memory.config import config_path
from tools.project_memory.services.knowledge import knowledge_conflict_count
from tools.project_memory.services.modules import module_states
from tools.project_memory.services.rationale import rationale_conflict_count
from tools.project_memory.services.status import project_status
from tools.project_memory.services.tasks import list_tasks


def build_memory_report(root: Path) -> dict[str, Any]:
    status = project_status(root)
    active_tasks = list_tasks(root)
    evals_dir = config_path(root, "evals_dir")
    eval_files = sorted(path.relative_to(root).as_posix() for path in evals_dir.glob("*.jsonl")) if evals_dir.exists() else []
    conflicts = {
        "knowledge": knowledge_conflict_count(root),
        "rationale": rationale_conflict_count(root),
    }
    attention = _attention(status["index"], conflicts, len(active_tasks), eval_files)
    return {
        "root": str(root),
        "ok": not attention,
        "attention": attention,
        "index": status["index"],
        "counts": status["counts"],
        "conflicts": conflicts,
        "tasks": {
            "active": len(active_tasks),
            "items": [task.__dict__ for task in active_tasks[:20]],
        },
        "evals": {
            "files": len(eval_files),
            "sample": eval_files[:10],
            "hint": _eval_hint(eval_files),
        },
        "modules": {state.name: {"enabled": state.enabled, "path": str(state.path) if state.path else None} for state in module_states(root)},
    }


def _attention(index: dict[str, Any], conflicts: dict[str, int], active_tasks: int, eval_files: list[str]) -> list[str]:
    items: list[str] = []
    if not index.get("fresh"):
        items.append("index is stale or incomplete")
    if conflicts["knowledge"]:
        items.append("knowledge conflicts need review")
    if conflicts["rationale"]:
        items.append("rationale conflicts need review")
    if active_tasks:
        items.append("active multi-agent tasks are waiting")
    if not eval_files:
        items.append("no memory eval files found")
    return items


def _eval_hint(eval_files: list[str]) -> str:
    if not eval_files:
        return "Add JSONL evals under .project-memory/evals/ for recurring memory checks."
    return f"Run ./pmem eval --file {eval_files[0]}"


def format_memory_report(report: dict[str, Any], fmt: str = "markdown") -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True)
    index = report["index"]
    counts = report["counts"]
    lines = [
        "# Memory Quality Report",
        "",
        f"- ok: {report['ok']}",
        (
            "- index: "
            f"fresh={index['fresh']} total={index['total_files']} indexed={index['indexed_files']} "
            f"missing={index['missing']} stale={index['stale']} removed={index['removed']}"
        ),
        f"- graph: nodes={counts['nodes']} edges={counts['edges']} chunks={counts['chunks']}",
        f"- conflicts: knowledge={report['conflicts']['knowledge']} rationale={report['conflicts']['rationale']}",
        f"- active tasks: {report['tasks']['active']}",
        f"- evals: files={report['evals']['files']} hint={report['evals']['hint']}",
        "- modules: " + ", ".join(
            f"{name}={'enabled' if data['enabled'] else 'disabled'}" for name, data in sorted(report["modules"].items())
        ),
    ]
    if index.get("sample"):
        lines.append("- stale sample: " + ", ".join(index["sample"]))
    lines.extend(["", "## Attention"])
    lines.extend(f"- {item}" for item in report["attention"]) if report["attention"] else lines.append("- none")
    if report["tasks"]["items"]:
        lines.extend(["", "## Active Tasks"])
        lines.extend(f"- [{item['status']}] {item['role']} {item['task_type']}: {item['title']}" for item in report["tasks"]["items"])
    return "\n".join(lines) + "\n"
