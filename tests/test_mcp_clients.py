from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import subprocess

from project_memory_kit.installer.install_project import install_project
from tools.project_memory.ignore import is_ignored

from tools.project_memory.services.mcp_config import build_mcp_config, format_mcp_config, write_mcp_config


class MCPClientsTest(unittest.TestCase):
    def test_json_clients_pin_same_root_and_preserve_other_servers(self):
        with tempfile.TemporaryDirectory(prefix="pmem clients ") as tmp:
            root = Path(tmp).resolve()
            for client, relative in (("claude", ".mcp.json"), ("kimi", ".kimi-code/mcp.json")):
                with self.subTest(client=client):
                    path = root / relative
                    path.parent.mkdir(exist_ok=True)
                    path.write_text(json.dumps({"custom": True, "mcpServers": {"other": {"command": "user-tool"}}}))
                    self.assertEqual(write_mcp_config(root, client), path)
                    result = json.loads(path.read_text())
                    self.assertTrue(result["custom"])
                    self.assertEqual(result["mcpServers"]["other"], {"command": "user-tool"})
                    self.assertEqual(result["mcpServers"]["project_memory"], {"command": str(root / "pmem"), "args": ["mcp", "--root", str(root)]})
                    before = (path.read_bytes(), path.stat().st_mtime_ns)
                    write_mcp_config(root, client)
                    self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))
                    self.assertEqual(json.loads(format_mcp_config(build_mcp_config(root, client)))["mcpServers"]["project_memory"], result["mcpServers"]["project_memory"])
            self.assertFalse((root / ".project-memory").exists())

    def test_invalid_or_conflicting_json_is_never_replaced(self):
        samples = ['{broken', '[]', 'null', '{"mcpServers": []}',
                   '{"mcpServers":{},"mcpServers":{}}',
                   '{"mcpServers":{"project_memory":{"command":"other-project"}}}']
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for client, relative in (("claude", ".mcp.json"), ("kimi", ".kimi-code/mcp.json")):
                path = root / relative
                path.parent.mkdir(exist_ok=True)
                for sample in samples:
                    with self.subTest(client=client, sample=sample):
                        path.write_text(sample)
                        with self.assertRaises(ValueError):
                            write_mcp_config(root, client)
                        self.assertEqual(path.read_text(), sample)
                        self.assertFalse(path.with_suffix(".json.bak").exists())

    def test_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            other = Path(tmp) / "other"
            root.mkdir(); other.mkdir()
            (root / ".kimi-code").symlink_to(other, target_is_directory=True)
            with self.assertRaises(ValueError):
                write_mcp_config(root, "kimi")
            (root / ".mcp.json").symlink_to(other / "missing.json")
            with self.assertRaises(ValueError):
                write_mcp_config(root, "claude")
            self.assertEqual(list(other.iterdir()), [])

    def test_default_codex_format_and_unknown_client(self):
        self.assertIn("[mcp_servers.project_memory]", format_mcp_config(build_mcp_config(Path("."))))
        with self.assertRaises(ValueError):
            build_mcp_config(Path("."), "unknown")

    def test_client_state_excluded_and_real_stdio_reads_same_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            install_project(root, no_git_init=True)
            for client, relative in (("claude", ".mcp.json"), ("kimi", ".kimi-code/mcp.json")):
                result = subprocess.run([str(root / "pmem"), "mcp-config", "--client", client, "--write"], cwd=root, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(is_ignored(root, root / relative))
                server = json.loads((root / relative).read_text())["mcpServers"]["project_memory"]
                requests = [
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "pmem-config-test", "version": "1"}}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "pmem_doctor", "arguments": {}}},
                ]
                reply = subprocess.run([server["command"], *server["args"]], cwd=Path(tmp).parent,
                    input="".join(json.dumps(r)+"\n" for r in requests), capture_output=True, text=True, timeout=30)
                self.assertEqual(reply.returncode, 0, reply.stderr)
                messages = {r["id"]: r for r in map(json.loads, reply.stdout.splitlines())}
                names = {t["name"] for t in messages[2]["result"]["tools"]}
                self.assertTrue({"pmem_context", "pmem_knowledge_add", "pmem_rationale_add"} <= names)
                self.assertFalse(messages[3]["result"].get("isError", False))
                self.assertIn(str(root / ".project-memory/graph.sqlite"), json.dumps(messages[3], ensure_ascii=False))
            self.assertFalse((root / ".git").exists())


if __name__ == "__main__":
    unittest.main()
