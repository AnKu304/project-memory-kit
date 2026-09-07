from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def build_mcp_config(root: Path, client: str = "generic") -> dict[str, Any]:
    if client not in {"claude", "kimi", "generic", "codex"}:
        raise ValueError("--client must be claude, kimi, codex, or generic")
    resolved = root.resolve()
    command = resolved / "pmem"
    if client in {"claude", "kimi"}:
        return {
            "mcpServers": {
                "project_memory": {
                    "command": str(command),
                    "args": ["mcp", "--root", str(resolved)],
                }
            }
        }
    return {
        "mcp_servers": {
            "project_memory": {
                "command": str(command),
                "args": ["mcp", "--root", str(resolved)],
            }
        }
    }


def format_mcp_config(config: dict[str, Any], fmt: str = "auto") -> str:
    if fmt == "auto":
        fmt = "json" if "mcpServers" in config else "toml"
    if fmt == "json":
        return json.dumps(config, indent=2, sort_keys=True) + "\n"
    if "mcpServers" in config:
        server = config["mcpServers"]["project_memory"]
    else:
        server = config["mcp_servers"]["project_memory"]
    args = ", ".join(json.dumps(item) for item in server["args"])
    return (
        "[mcp_servers.project_memory]\n"
        f"command = {json.dumps(server['command'])}\n"
        f"args = [{args}]\n"
    )


def _checked_path(root: Path, relative: str) -> Path:
    path = root
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("MCP config paths must not contain symlinks")
    return path


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key in MCP config; reconcile manually")
        result[key] = value
    return result


def _atomic_config(path: Path, text: str, previous: bytes | None) -> None:
    if previous == text.encode("utf-8"):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".pmem-config-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink() or (path.read_bytes() if path.exists() else None) != previous:
            raise ValueError("MCP config changed during write; retry after reconciliation")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_mcp_config(root: Path, client: str = "claude") -> Path:
    root = root.resolve(strict=True)
    config = build_mcp_config(root, client)
    if client in {"claude", "kimi"}:
        relative = ".mcp.json" if client == "claude" else ".kimi-code/mcp.json"
        path = _checked_path(root, relative)
        current: dict[str, Any] = {}
        previous = path.read_bytes() if path.exists() else None
        if previous is not None:
            try:
                current = json.loads(previous.decode("utf-8"), object_pairs_hook=_unique_object)
            except json.JSONDecodeError:
                raise ValueError("Invalid MCP JSON; existing file preserved") from None
        if not isinstance(current, dict) or not isinstance(current.get("mcpServers", {}), dict):
            raise ValueError("MCP config and mcpServers must be JSON objects")
        servers = current.setdefault("mcpServers", {})
        expected = config["mcpServers"]["project_memory"]
        if "project_memory" in servers:
            if servers["project_memory"] != expected:
                raise ValueError("Existing project_memory differs; reconcile explicitly without overwriting")
            return path
        servers["project_memory"] = expected
        _atomic_config(path, json.dumps(current, indent=2, sort_keys=True) + "\n", previous)
        return path
    path = _checked_path(root, f".project-memory/reports/{client}-mcp-config.toml")
    _atomic_config(path, format_mcp_config(config, "toml"), path.read_bytes() if path.exists() else None)
    return path
