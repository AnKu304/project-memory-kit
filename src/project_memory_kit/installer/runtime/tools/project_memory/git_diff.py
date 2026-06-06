from __future__ import annotations

import re
import subprocess
from pathlib import Path


def git_available(root: Path) -> bool:
    return (root / ".git").exists()


def run_git(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def changed_files(root: Path, base: str = "HEAD") -> list[str]:
    if not git_available(root):
        return []
    result = run_git(root, ["diff", "--name-only", base])
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def diff_ranges(root: Path, base: str = "HEAD") -> dict[str, list[tuple[int, int]]]:
    if not git_available(root):
        return {}
    result = run_git(root, ["diff", "--unified=0", base])
    if result.returncode != 0:
        return {}
    ranges: dict[str, list[tuple[int, int]]] = {}
    current: str | None = None
    file_re = re.compile(r"^\+\+\+ b/(.+)$")
    hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
    for line in result.stdout.splitlines():
        file_match = file_re.match(line)
        if file_match:
            current = file_match.group(1)
            ranges.setdefault(current, [])
            continue
        hunk_match = hunk_re.match(line)
        if hunk_match and current:
            start = int(hunk_match.group(1))
            count = int(hunk_match.group(2) or "1")
            end = max(start, start + count - 1)
            ranges[current].append((start, end))
    return ranges

