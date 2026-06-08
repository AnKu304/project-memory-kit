from __future__ import annotations

from pathlib import Path

from tools.project_memory.config import config_path, load_config
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.services.impact_analysis import analyze_impact


def select_tests(root: Path, base: str = "HEAD") -> list[str]:
    impact = analyze_impact(root, base)
    commands: list[str] = []
    for item in impact["tests"]:
        target = item["target"]
        if target.endswith(".py"):
            commands.append(f"python -m unittest {target}")
        else:
            commands.append(target)
    if not commands:
        commands.extend(load_config(root).get("tests", {}).get("default_commands", ["python -m unittest discover"]))
    return list(dict.fromkeys(commands))


def explain_tests(root: Path, base: str = "HEAD") -> str:
    impact = analyze_impact(root, base)
    commands = select_tests(root, base)
    reasons = {item["target"]: item["reason"] for item in impact["tests"]}
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    failures = store.query(
        """
        SELECT fingerprint, error_kind, normalized_message, last_seen_at, count
        FROM failure_fingerprints
        ORDER BY last_seen_at DESC
        LIMIT 5
        """
    )
    lines = [
        "Test Plan",
        f"- base: {base}",
        f"- risk: {impact['risk']}",
        f"- changed_files: {len(impact['changed_files'])}",
        f"- affected_files: {len(impact['affected_files'])}",
        "",
        "## Commands",
    ]
    for command in commands:
        reason = reasons.get(command) or "configured default or package test command"
        lines.append(f"- `{command}`: {reason}")
    lines.extend(["", "## Recent Failures"])
    if failures:
        for row in failures:
            lines.append(
                f"- `{row['fingerprint']}` {row['error_kind']}: "
                f"{row['normalized_message']} ({row['count']}x, last {row['last_seen_at']})"
            )
    else:
        lines.append("- No prior failures recorded.")
    return "\n".join(lines) + "\n"
