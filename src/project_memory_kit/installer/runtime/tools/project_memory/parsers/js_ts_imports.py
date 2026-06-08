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
    candidates.extend(_package_candidates(root, specifier))
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


def _package_candidates(root: Path, specifier: str) -> list[Path]:
    candidates: list[Path] = []
    for package_root, name, exports in _workspace_packages(root):
        if not name:
            continue
        if specifier == name:
            candidates.extend(_entry_candidates(package_root, exports))
            continue
        prefix = name + "/"
        if specifier.startswith(prefix):
            tail = specifier[len(prefix) :]
            candidates.append((package_root / tail).resolve())
            candidates.append((package_root / "src" / tail).resolve())
    return candidates


def _entry_candidates(package_root: Path, exports: Any) -> list[Path]:
    candidates = [package_root / "src" / "index", package_root / "index"]
    target = _export_target(exports)
    if target:
        candidates.insert(0, package_root / target)
    package_json = package_root / "package.json"
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    for key in ("module", "main", "types"):
        value = data.get(key)
        if isinstance(value, str):
            candidates.append(package_root / value)
    return [candidate.resolve() for candidate in candidates]


def _export_target(exports: Any) -> str | None:
    if isinstance(exports, str):
        return exports
    if isinstance(exports, dict):
        entry = exports.get(".") if "." in exports else exports
        if isinstance(entry, str):
            return entry
        if isinstance(entry, dict):
            for key in ("import", "default", "require", "types"):
                value = entry.get(key)
                if isinstance(value, str):
                    return value
    return None


@lru_cache(maxsize=32)
def _workspace_packages(root: Path) -> tuple[tuple[Path, str, Any], ...]:
    packages: list[tuple[Path, str, Any]] = []
    root_package = _read_package_json(root / "package.json")
    if root_package:
        packages.append((root, str(root_package.get("name") or ""), root_package.get("exports")))
    for pattern in _workspace_patterns(root_package):
        for package_json in sorted(root.glob(pattern.rstrip("/") + "/package.json")):
            package_root = package_json.parent
            data = _read_package_json(package_json)
            if data:
                packages.append((package_root, str(data.get("name") or ""), data.get("exports")))
    return tuple(packages)


def _workspace_patterns(package_data: dict[str, Any]) -> list[str]:
    raw = package_data.get("workspaces", []) if package_data else []
    if isinstance(raw, dict):
        raw = raw.get("packages", [])
    if isinstance(raw, str):
        raw = [raw]
    return [str(item) for item in raw if isinstance(item, str)]


def _read_package_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(_strip_json_comments(path.read_text(encoding="utf-8", errors="replace")))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _strip_json_comments(text: str) -> str:
    text = re.sub(r"//.*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text
