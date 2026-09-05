from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.project_memory.config import config_path, load_config
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.services.impact_analysis import analyze_impact


class TestSelection(list):
    """Commands plus availability metadata, without pretending warnings are commands."""
    def __init__(self, commands=(), *, diagnostics=()):
        super().__init__(commands)
        self.diagnostics = list(diagnostics)


class TestExplanation(str):
    """Formatted explanation with the same diagnostics as its command list."""
    def __new__(cls, text, diagnostics=()):
        result = super().__new__(cls, text)
        result.diagnostics = list(diagnostics)
        return result


def select_tests(root: Path, base: str = "HEAD", *, impact: dict[str, Any] | None = None) -> list[str]:
    if impact is None:
        impact = analyze_impact(root, base)
    if not impact.get("git_available", True):
        defaults = load_config(root).get("tests", {}).get("default_commands", [])
        return TestSelection(defaults, diagnostics=[*impact.get("diagnostics", []),
            "Configured fallback checks only; no Git-derived targeted test selection is available."])
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
    commands = select_tests(root, base, impact=impact)
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
        f"- changed_files: {len(impact['changed_files']) if impact.get('git_available', True) else 'unavailable'}",
        f"- affected_files: {len(impact['affected_files'])}",
        "",
        "## Commands",
    ]
    lines.extend(f"- Warning: {item}" for item in getattr(commands, "diagnostics", []))
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
    return TestExplanation("\n".join(lines) + "\n", getattr(commands, "diagnostics", []))
