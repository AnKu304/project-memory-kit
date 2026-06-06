from __future__ import annotations

from pathlib import Path


def module_name_for_path(root: Path, path: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def resolve_module(root: Path, current: Path, module: str, level: int = 0) -> str | None:
    if level:
        package = current.parent
        for _ in range(max(level - 1, 0)):
            package = package.parent
        base = package
    else:
        base = root
    parts = module.split(".") if module else []
    candidate = base.joinpath(*parts)
    for path in [candidate.with_suffix(".py"), candidate / "__init__.py"]:
        if path.exists() and path.is_file():
            return path.relative_to(root).as_posix()
    return None

