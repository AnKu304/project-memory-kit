from __future__ import annotations

from pathlib import Path

from tools.project_memory.config import load_config
from tools.project_memory.services.impact_analysis import analyze_impact


def select_tests(root: Path, base: str = "HEAD") -> list[str]:
    impact = analyze_impact(root, base)
    commands: list[str] = []
    for item in impact["tests"]:
        target = item["target"]
        if target.endswith(".py") or target.startswith("tests/"):
            commands.append(f"python -m unittest {target}")
        else:
            commands.append(target)
    if not commands:
        commands.extend(load_config(root).get("tests", {}).get("default_commands", ["python -m unittest discover"]))
    return list(dict.fromkeys(commands))

