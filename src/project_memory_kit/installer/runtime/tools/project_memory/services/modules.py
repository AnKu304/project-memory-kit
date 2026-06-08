from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.project_memory.config import DEFAULT_CONFIG, config_path, deep_merge, load_config

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


@dataclass(frozen=True)
class ModuleState:
    name: str
    enabled: bool
    path_key: str | None = None
    path: Path | None = None
    description: str = ""


MODULES: dict[str, dict[str, str]] = {
    "human": {
        "path_key": "human_dir",
        "description": "optional human-facing Markdown/export layer; disabled by default",
    },
}


def _config_file(root: Path) -> Path:
    return root / ".project-memory" / "config.yaml"


def _read_raw_config(root: Path) -> dict[str, Any]:
    path = _config_file(root)
    if not path.exists() or yaml is None:
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _write_raw_config(root: Path, data: dict[str, Any]) -> None:
    if yaml is None:
        raise RuntimeError("PyYAML is required to update project-memory modules")
    path = _config_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    path.write_text(rendered, encoding="utf-8")


def _read_module_enabled_from_text(root: Path, name: str) -> bool | None:
    path = _config_file(root)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    pattern = rf"(?ms)^modules:\s*\n(?:^[ \t]+.*\n)*?^[ \t]{{2}}{re.escape(name)}:\s*\n(?:^[ \t]{{4}}(?!enabled:).*\n)*?^[ \t]{{4}}enabled:\s*(true|false)\s*$"
    match = re.search(pattern, text)
    if not match:
        return None
    return match.group(1).lower() == "true"


def _write_module_enabled_to_text(root: Path, name: str, enabled: bool) -> None:
    path = _config_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    value = "true" if enabled else "false"
    if not path.exists():
        path.write_text(f"modules:\n  {name}:\n    enabled: {value}\n", encoding="utf-8")
        return
    text = path.read_text(encoding="utf-8")
    pattern = rf"(?ms)(^modules:\s*\n(?:^[ \t]+.*\n)*?^[ \t]{{2}}{re.escape(name)}:\s*\n(?:^[ \t]{{4}}(?!enabled:).*\n)*?^[ \t]{{4}}enabled:\s*)(true|false)(\s*$)"
    if re.search(pattern, text):
        text = re.sub(pattern, rf"\g<1>{value}\g<3>", text, count=1)
    elif re.search(r"(?m)^modules:\s*$", text):
        text = re.sub(r"(?m)^modules:\s*$", f"modules:\n  {name}:\n    enabled: {value}", text, count=1)
    else:
        text = text.rstrip() + f"\nmodules:\n  {name}:\n    enabled: {value}\n"
    path.write_text(text, encoding="utf-8")


def module_states(root: Path) -> list[ModuleState]:
    cfg = load_config(root)
    states: list[ModuleState] = []
    for name, meta in MODULES.items():
        module_cfg = cfg.get("modules", {}).get(name, {})
        text_enabled = _read_module_enabled_from_text(root, name) if yaml is None else None
        path_key = meta.get("path_key")
        path = config_path(root, path_key) if path_key else None
        states.append(
            ModuleState(
                name=name,
                enabled=bool(module_cfg.get("enabled", False) if text_enabled is None else text_enabled),
                path_key=path_key,
                path=path,
                description=meta.get("description", ""),
            )
        )
    return states


def module_enabled(root: Path, name: str) -> bool:
    normalized = name.strip().lower()
    for state in module_states(root):
        if state.name == normalized:
            return state.enabled
    raise ValueError(f"unknown project-memory module: {name}")


def ensure_enabled_module_paths(root: Path) -> None:
    for state in module_states(root):
        if state.enabled and state.path:
            state.path.mkdir(parents=True, exist_ok=True)


def set_module_enabled(root: Path, name: str, enabled: bool) -> ModuleState:
    normalized = name.strip().lower()
    if normalized not in MODULES:
        raise ValueError(f"unknown project-memory module: {name}")

    if yaml is None:
        _write_module_enabled_to_text(root, normalized, enabled)
        state = next(item for item in module_states(root) if item.name == normalized)
        if state.enabled and state.path:
            state.path.mkdir(parents=True, exist_ok=True)
        return state

    raw = _read_raw_config(root)
    # Preserve user formatting only at semantic level. The installer already uses YAML merge semantics.
    merged = deep_merge(DEFAULT_CONFIG, raw)
    merged.setdefault("modules", {}).setdefault(normalized, {})["enabled"] = enabled
    _write_raw_config(root, merged)

    state = next(item for item in module_states(root) if item.name == normalized)
    if state.enabled and state.path:
        state.path.mkdir(parents=True, exist_ok=True)
    return state


def format_module_states(root: Path) -> str:
    lines = ["Project memory modules"]
    for state in module_states(root):
        status = "enabled" if state.enabled else "disabled"
        path = f" path={state.path}" if state.path else ""
        lines.append(f"- {state.name}: {status}{path}")
    return "\n".join(lines)
