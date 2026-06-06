from __future__ import annotations

from importlib import resources
from pathlib import Path


def installer_root() -> Path:
    return Path(str(resources.files("project_memory_kit.installer")))


def template_path(name: str) -> Path:
    return installer_root() / "templates" / name


def runtime_root() -> Path:
    return installer_root() / "runtime"


def skill_root() -> Path:
    return installer_root() / "skill" / "dependency-graph-rag"


def read_template(name: str) -> str:
    return template_path(name).read_text(encoding="utf-8")

