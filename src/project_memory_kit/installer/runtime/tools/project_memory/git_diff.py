from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def non_git_container(root: Path) -> bool:
    marker = root / ".project-memory" / "install.json"
    try:
        return json.loads(marker.read_text(encoding="utf-8")).get("installation_mode") == "non_git_container"
    except (OSError, ValueError, AttributeError):
        return False


def git_available(root: Path) -> bool:
    return not non_git_container(root) and (root / ".git").exists()


def git_limitation(root: Path) -> str | None:
    if git_available(root):
        return None
    return ("Git impact and diff-based test selection are unavailable for this root. "
            "Nested repositories are indexed as sources; cross-repository Git diff is not implemented.")


def run_git(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    if not git_available(root):
        return subprocess.CompletedProcess(["git", *args], 1, "", git_limitation(root) or "Git unavailable")
    return subprocess.run(["git", *args], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def changed_files(root: Path, base: str = "HEAD") -> list[str]:
    if not git_available(root):
        return []
    result = run_git(root, ["diff", "--name-only", base])
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def untracked_files(root: Path) -> list[str]:
    if not git_available(root):
        return []
    result = run_git(root, ["ls-files", "--others", "--exclude-standard"])
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
