from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


@dataclass
class InstallReport:
    target: Path
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    preserved: list[str] = field(default_factory=list)
    backed_up: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)

    def add_path(self, bucket: str, path: Path) -> None:
        rel = str(path.relative_to(self.target)) if path.is_relative_to(self.target) else str(path)
        getattr(self, bucket).append(rel)

    def summary(self) -> str:
        lines = [f"project-memory-kit installed in {self.target}"]
        for title, values in [
            ("created", self.created),
            ("updated", self.updated),
            ("preserved", self.preserved),
            ("backed up", self.backed_up),
            ("commands", self.commands),
        ]:
            if values:
                lines.append(f"{title}:")
                lines.extend(f"  - {value}" for value in values)
        return "\n".join(lines)


def write_managed_file(src: Path, dest: Path, report: InstallReport, executable: bool = False) -> None:
    data = src.read_bytes()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        existing = dest.read_bytes()
        if existing == data:
            report.add_path("preserved", dest)
        else:
            backup = dest.with_name(f"{dest.name}.bak.{timestamp()}")
            shutil.copy2(dest, backup)
            report.add_path("backed_up", backup)
            dest.write_bytes(data)
            report.add_path("updated", dest)
    else:
        dest.write_bytes(data)
        report.add_path("created", dest)
    if executable:
        dest.chmod(dest.stat().st_mode | 0o755)


def write_text_file(path: Path, content: str, report: InstallReport, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8")
    if path.exists():
        if path.read_bytes() == data:
            report.add_path("preserved", path)
        else:
            backup = path.with_name(f"{path.name}.bak.{timestamp()}")
            shutil.copy2(path, backup)
            report.add_path("backed_up", backup)
            path.write_bytes(data)
            report.add_path("updated", path)
    else:
        path.write_bytes(data)
        report.add_path("created", path)
    if executable:
        path.chmod(path.stat().st_mode | 0o755)

