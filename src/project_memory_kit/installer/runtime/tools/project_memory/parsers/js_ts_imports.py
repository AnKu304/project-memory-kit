from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


JS_TS_EXTENSIONS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts")
RESOLVABLE_EXTENSIONS = (
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mts",
    ".cts",
    ".mjs",
    ".cjs",
    ".json",
    ".css",
    ".scss",
    ".sass",
    ".less",
)


def module_name_for_path(root: Path, path: Path) -> str:
    root = root.resolve()
    path = path.resolve()
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "index":
        parts = parts[:-1]
    return ".".join(parts)


def language_for_path(path: Path) -> str:
    if path.suffix in {".ts", ".tsx", ".mts", ".cts"}:
        return "typescript"
    return "javascript"


def resolve_module(root: Path, current: Path, specifier: str) -> str | None:
    if not specifier:
        return None
    root = root.resolve()
    current = current.resolve()

    candidates: list[Path] = []
    if specifier.startswith("."):
        candidates.append((current.parent / specifier).resolve())
    elif specifier.startswith("/"):
        candidates.append((root / specifier.lstrip("/")).resolve())
    else:
        candidates.extend(_alias_candidates(root, specifier))

    for candidate in candidates:
        resolved = _resolve_candidate(candidate)
        if resolved and resolved.is_relative_to(root):
            return resolved.relative_to(root).as_posix()
    return None


def _resolve_candidate(candidate: Path) -> Path | None:
    if candidate.is_file():
        return candidate
    if candidate.suffix:
        return candidate if candidate.is_file() else None
    for ext in RESOLVABLE_EXTENSIONS:
        path = candidate.with_suffix(ext)
        if path.is_file():
            return path
    if candidate.is_dir():
        for ext in RESOLVABLE_EXTENSIONS:
            path = candidate / f"index{ext}"
            if path.is_file():
                return path
    return None


def _alias_candidates(root: Path, specifier: str) -> list[Path]:
    candidates = []
    for base, pattern, replacement in _alias_rules(root):
        match = _match_alias(pattern, specifier)
        if match is None:
            continue
        target = replacement.replace("*", match)
        candidates.append((base / target).resolve())
    if specifier.startswith("@/"):
        tail = specifier[2:]
        candidates.append((root / "src" / tail).resolve())
        candidates.append((root / tail).resolve())
    return candidates


def _match_alias(pattern: str, specifier: str) -> str | None:
    if "*" not in pattern:
        return "" if pattern == specifier else None
    prefix, suffix = pattern.split("*", 1)
    if not specifier.startswith(prefix) or not specifier.endswith(suffix):
        return None
    return specifier[len(prefix) : len(specifier) - len(suffix) if suffix else None]


@lru_cache(maxsize=32)
def _alias_rules(root: Path) -> tuple[tuple[Path, str, str], ...]:
    data = _read_project_config(root)
    compiler = data.get("compilerOptions", {}) if isinstance(data, dict) else {}
    base_url = compiler.get("baseUrl", ".")
    base = (root / base_url).resolve() if isinstance(base_url, str) else root
    paths = compiler.get("paths", {})
    rules: list[tuple[Path, str, str]] = []
    if isinstance(paths, dict):
        for pattern, replacements in paths.items():
            if not isinstance(pattern, str):
                continue
            if isinstance(replacements, str):
                replacements = [replacements]
            if isinstance(replacements, list):
                for replacement in replacements:
                    if isinstance(replacement, str):
                        rules.append((base, pattern, replacement))
    rules.extend(((root, "@/*", "src/*"), (root, "@/*", "*")))
    return tuple(rules)


def _read_project_config(root: Path) -> dict[str, Any]:
    for name in ("tsconfig.json", "jsconfig.json"):
        path = root / name
        if not path.exists():
            continue
        try:
            return json.loads(_strip_json_comments(path.read_text(encoding="utf-8", errors="replace")))
        except Exception:
            return {}
    return {}


def _strip_json_comments(text: str) -> str:
    text = re.sub(r"//.*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text
