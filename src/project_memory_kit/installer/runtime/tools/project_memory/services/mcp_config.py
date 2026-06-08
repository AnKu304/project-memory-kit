from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_mcp_config(root: Path, client: str = "generic") -> dict[str, Any]:
    resolved = root.resolve()
    command = resolved / "pmem"
    if client == "claude":
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


def format_mcp_config(config: dict[str, Any], fmt: str = "toml") -> str:
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


def write_mcp_config(root: Path, client: str = "claude") -> Path:
    if client not in {"claude", "generic", "codex"}:
        raise ValueError("--client must be claude, codex, or generic")
    if client == "claude":
        path = root / ".mcp.json"
        current: dict[str, Any] = {}
        if path.exists():
            try:
                current = json.loads(path.read_text(encoding="utf-8")) or {}
            except json.JSONDecodeError:
                backup = path.with_suffix(path.suffix + ".bak")
                backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
                current = {}
        config = build_mcp_config(root, client="claude")
        servers = current.setdefault("mcpServers", {})
        servers["project_memory"] = config["mcpServers"]["project_memory"]
        path.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path
    path = root / ".project-memory" / "reports" / f"{client}-mcp-config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_mcp_config(build_mcp_config(root), "toml"), encoding="utf-8")
    return path
