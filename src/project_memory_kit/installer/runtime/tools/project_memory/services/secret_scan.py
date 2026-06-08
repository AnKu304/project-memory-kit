from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.project_memory.config import load_config
from tools.project_memory.ignore import is_binary


DEPENDENCY_DIRS = {
    ".git",
    ".project-memory",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".next",
    "dist",
    "build",
    ".cache",
}

SECRET_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{24,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{30,}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b")),
    (
        "secret_assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret|password)\b"
            r"\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"
        ),
    ),
]


@dataclass(frozen=True)
class SecretFinding:
    path: str
    line: int
    rule: str
    fingerprint: str


def _should_scan(root: Path, path: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    if any(part in DEPENDENCY_DIRS for part in rel.parts):
        return False
    if rel.as_posix().startswith("tools/project_memory/"):
        return False
    if not path.is_file() or is_binary(path):
        return False
    return True


def _fingerprint(rule: str, path: str, line: int, match: str) -> str:
    import hashlib

    digest = hashlib.sha256(f"{rule}:{path}:{line}:{match[:12]}".encode("utf-8")).hexdigest()
    return digest[:16]


def scan_secrets(root: Path, max_findings: int | None = None) -> list[SecretFinding]:
    cfg = load_config(root)
    secret_cfg = cfg.get("audit", {}).get("secrets", {})
    max_file_bytes = int(secret_cfg.get("max_file_bytes") or 1_000_000)
    limit = int(max_findings or secret_cfg.get("max_findings") or 100)
    findings: list[SecretFinding] = []

    for path in sorted(root.rglob("*")):
        if len(findings) >= limit:
            break
        if not _should_scan(root, path):
            continue
        try:
            if path.stat().st_size > max_file_bytes:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        for line_number, line in enumerate(text.splitlines(), start=1):
            for rule, pattern in SECRET_RULES:
                match = pattern.search(line)
                if not match:
                    continue
                findings.append(
                    SecretFinding(
                        path=rel,
                        line=line_number,
                        rule=rule,
                        fingerprint=_fingerprint(rule, rel, line_number, match.group(0)),
                    )
                )
                break
            if len(findings) >= limit:
                break

    return findings


def format_secret_scan(findings: list[SecretFinding], fmt: str = "markdown") -> str:
    payload: list[dict[str, Any]] = [
        {
            "path": item.path,
            "line": item.line,
            "rule": item.rule,
            "fingerprint": item.fingerprint,
        }
        for item in findings
    ]
    if fmt == "json":
        return json.dumps({"findings": payload, "count": len(payload)}, indent=2, sort_keys=True)
    lines = [f"Secret Scan: findings={len(findings)}"]
    for item in findings:
        lines.append(f"- warning {item.rule}: {item.path}:{item.line} fingerprint={item.fingerprint}")
    return "\n".join(lines) + "\n"
