from __future__ import annotations

from pathlib import Path

from project_memory_kit.installer.manifest import InstallReport, write_managed_file


def copy_tree(src_root: Path, dest_root: Path, report: InstallReport) -> None:
    for src in sorted(src_root.rglob("*")):
        if src.is_dir():
            continue
        if "__pycache__" in src.parts or src.suffix in {".pyc", ".pyo"}:
            continue
        rel = src.relative_to(src_root)
        dest = dest_root / rel
        write_managed_file(src, dest, report)
