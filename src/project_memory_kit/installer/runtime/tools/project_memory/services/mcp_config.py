from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_mcp_config(root: Path) -> dict[str, Any]:
    resolved = root.resolve()
    command = resolved / "pmem"
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
    server = config["mcp_servers"]["project_memory"]
    args = ", ".join(json.dumps(item) for item in server["args"])
    return (
        "[mcp_servers.project_memory]\n"
        f"command = {json.dumps(server['command'])}\n"
        f"args = [{args}]\n"
    )
