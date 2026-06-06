from __future__ import annotations

import re
from pathlib import Path

from project_memory_kit.installer.manifest import InstallReport

BEGIN = "<!-- PMEM:BEGIN -->"
END = "<!-- PMEM:END -->"


def managed_block(body: str) -> str:
    body = body.strip()
    return f"{BEGIN}\n{body}\n{END}\n"


def merge_agents_block(path: Path, body: str, report: InstallReport, full_template: str | None = None) -> None:
    block = managed_block(body)
    if not path.exists():
        if full_template:
            content = full_template.rstrip() + "\n\n" + block
        else:
            content = block
        path.write_text(content, encoding="utf-8")
        report.add_path("created", path)
        return

    original = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"{re.escape(BEGIN)}.*?{re.escape(END)}\n?", re.S)
    if pattern.search(original):
        updated = pattern.sub(block, original)
    else:
        sep = "" if original.endswith("\n\n") else "\n\n" if original.endswith("\n") else "\n\n"
        updated = original + sep + block

    if updated == original:
        report.add_path("preserved", path)
    else:
        path.write_text(updated, encoding="utf-8")
        report.add_path("updated", path)


def remove_agents_block(path: Path, report: InstallReport) -> None:
    if not path.exists():
        return
    original = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"\n?{re.escape(BEGIN)}.*?{re.escape(END)}\n?", re.S)
    updated = pattern.sub("\n", original).strip() + "\n"
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        report.add_path("updated", path)
