from __future__ import annotations

import hashlib
import json
import subprocess
import sqlite3
import tempfile
import unittest
from pathlib import Path

from project_memory_kit.installer.install_project import install_project


class RuntimeCommandsTest(unittest.TestCase):
    def test_status_search_debug_eval_audit_and_tests_explain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )
            (root / "app.py").write_text(
                "def alpha_payment_validator(amount):\n"
                "    return amount >= 0\n",
                encoding="utf-8",
            )

            status_before = subprocess.run(
                [str(root / "pmem"), "status"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(status_before.returncode, 0, status_before.stderr)
            self.assertIn("fresh=False", status_before.stdout)
            self.assertIn("missing=", status_before.stdout)
            self.assertIn("app.py", status_before.stdout)

            search = subprocess.run(
                [str(root / "pmem"), "search", "--query", "alpha payment validator", "--limit", "5", "--debug"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(search.returncode, 0, search.stderr)
            self.assertIn("[hybrid", search.stdout)
            self.assertIn("components=", search.stdout)
            self.assertIn("bm25", search.stdout)

            evals = root / ".project-memory" / "evals"
            evals.mkdir(parents=True, exist_ok=True)
            eval_file = evals / "search.jsonl"
            eval_file.write_text(
                json.dumps({"query": "alpha payment validator", "expect_path": "app.py"}) + "\n",
                encoding="utf-8",
            )
            evaluation = subprocess.run(
                [str(root / "pmem"), "eval", "--file", str(eval_file)],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(evaluation.returncode, 0, evaluation.stderr)
            self.assertIn("passed=1", evaluation.stdout)
            self.assertIn("failed=0", evaluation.stdout)

            audit = subprocess.run(
                [str(root / "pmem"), "audit"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(audit.returncode, 0, audit.stderr)
            self.assertIn("Memory Audit", audit.stdout)
            self.assertIn("index_fresh=True", audit.stdout)

            stale = subprocess.run(
                [str(root / "pmem"), "stale"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(stale.returncode, 0, stale.stderr)
            self.assertIn("fresh=True", stale.stdout)

            explained_tests = subprocess.run(
                [str(root / "pmem"), "tests", "--explain"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(explained_tests.returncode, 0, explained_tests.stderr)
            self.assertIn("Test Plan", explained_tests.stdout)

            watch = subprocess.run(
                [str(root / "pmem"), "watch", "--once"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(watch.returncode, 0, watch.stderr)
            self.assertIn("watch check", watch.stdout)

    def test_compiled_context_includes_evidence_gates_lifecycle_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root)
            (root / "app.py").write_text("def alpha_payment():\n    return False\n", encoding="utf-8")
            tests_dir = root / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_app.py").write_text("from app import alpha_payment\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py", "tests/test_app.py"], cwd=root)
            subprocess.run(["git", "commit", "-m", "init"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )
            notes = root / "notes"
            notes.mkdir()
            (notes / "rationale.md").write_text("# Payment Rationale\n\nUse non-negative checks.\n", encoding="utf-8")
            subprocess.run(
                [
                    str(root / "pmem"),
                    "rationale",
                    "add",
                    "--type",
                    "decision",
                    "--title",
                    "Payment Rationale",
                    "--file",
                    "notes/rationale.md",
                    "--why",
                    "avoids invalid payments",
                    "--evidence",
                    "tests/test_app.py",
                ],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                [str(root / "pmem"), "index", "--mode", "full"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            (root / "app.py").write_text("def alpha_payment():\n    return True\n", encoding="utf-8")

            context = subprocess.run(
                [
                    str(root / "pmem"),
                    "context",
                    "--task",
                    "alpha payment",
                    "--compiled",
                    "--out",
                    ".project-memory/reports/COMPILED.md",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(context.returncode, 0, context.stderr)
            content = (root / ".project-memory/reports/COMPILED.md").read_text(encoding="utf-8")
            self.assertIn("# Compiled Project Context", content)
            self.assertIn("## Local Evidence", content)
            self.assertIn("## Preflight Gate", content)
            self.assertIn("## Memory Lifecycle", content)
            self.assertIn("## Provenance", content)
            self.assertIn("components:", content)
            self.assertIn("tests/test_app.py", content)
            self.assertIn("evidence: tests/test_app.py", content)

    def test_js_ts_test_binding_and_builtin_golden_eval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root)
            src = root / "src"
            src.mkdir()
            (root / "package.json").write_text(
                json.dumps({"scripts": {"test": "vitest run"}}),
                encoding="utf-8",
            )
            (src / "Button.tsx").write_text(
                "export function Button() {\n  return <button>Pay</button>\n}\n",
                encoding="utf-8",
            )
            (src / "Button.test.tsx").write_text(
                "import { Button } from './Button'\nButton()\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "package.json", "src/Button.tsx", "src/Button.test.tsx"], cwd=root)
            subprocess.run(["git", "commit", "-m", "init"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )
            index = subprocess.run(
                [str(root / "pmem"), "index", "--mode", "full"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(index.returncode, 0, index.stderr)
            self.assertIn("test_bindings=", index.stdout)

            evaluation = subprocess.run(
                [str(root / "pmem"), "eval"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(evaluation.returncode, 0, evaluation.stderr)
            self.assertIn("golden-js-ts-file", evaluation.stdout)
            self.assertIn("failed=0", evaluation.stdout)

            (src / "Button.tsx").write_text(
                "export function Button() {\n  return <button>Checkout</button>\n}\n",
                encoding="utf-8",
            )
            impact = subprocess.run(
                [str(root / "pmem"), "impact", "--base", "HEAD"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(impact.returncode, 0, impact.stderr)
            self.assertIn("npm test -- src/Button.test.tsx", impact.stdout)
            self.assertIn("confidence=0.72", impact.stdout)

    def test_report_summarizes_memory_quality_as_markdown_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root, agent="multiagent")
            (root / "app.py").write_text("def report_token():\n    return True\n", encoding="utf-8")
            task = root / ".agents/tasks/review-report.md"
            task.write_text(
                "# Review Report\n\nType: handoff\nStatus: active\nRole: reviewer\n",
                encoding="utf-8",
            )

            markdown = subprocess.run(
                [str(root / "pmem"), "report"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(markdown.returncode, 0, markdown.stderr)
            self.assertIn("Memory Quality Report", markdown.stdout)
            self.assertIn("active tasks: 1", markdown.stdout)
            self.assertIn("index is stale or incomplete", markdown.stdout)

            as_json = subprocess.run(
                [str(root / "pmem"), "report", "--format", "json"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(as_json.returncode, 0, as_json.stderr)
            report = json.loads(as_json.stdout)
            self.assertFalse(report["ok"])
            self.assertEqual(report["tasks"]["active"], 1)
            self.assertIn("index", report)
            self.assertIn("evals", report)

    def test_watch_serve_indexes_hash_changed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )
            path = root / "app.py"
            path.write_text("def watch_token():\n    return 'before'\n", encoding="utf-8")
            subprocess.run(
                [str(root / "pmem"), "index", "--mode", "full"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            path.write_text("def watch_token():\n    return 'after'\n", encoding="utf-8")

            watch = subprocess.run(
                [str(root / "pmem"), "watch", "--serve", "--interval", "0", "--max-runs", "1"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(watch.returncode, 0, watch.stderr)
            self.assertIn("watch serve", watch.stdout)
            self.assertIn("watch check 1: indexed", watch.stdout)
            expected_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            conn = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                row = conn.execute("SELECT hash FROM file_index_state WHERE path = 'app.py'").fetchone()
            finally:
                conn.close()
            self.assertEqual(row[0], expected_hash)

    def test_search_auto_indexes_and_uses_bm25(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )
            (root / "app.py").write_text(
                "def alpha_payment_validator(amount):\n"
                "    return amount >= 0\n",
                encoding="utf-8",
            )

            search = subprocess.run(
                [str(root / "pmem"), "search", "--query", "alpha payment validator", "--limit", "5"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(search.returncode, 0, search.stderr)
            self.assertIn("app.py", search.stdout)
            self.assertIn("[hybrid", search.stdout)
            self.assertIn("bm25", search.stdout)

            conn = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                row = conn.execute("SELECT hash FROM file_index_state WHERE path = 'app.py'").fetchone()
            finally:
                conn.close()
            self.assertIsNotNone(row)

    def test_auto_index_removes_deleted_file_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )
            path = root / "app.py"
            path.write_text("def deleted_token_handler():\n    return True\n", encoding="utf-8")
            subprocess.run(
                [str(root / "pmem"), "index", "--mode", "full"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            path.unlink()

            search = subprocess.run(
                [str(root / "pmem"), "search", "--query", "deleted token handler", "--limit", "5"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(search.returncode, 0, search.stderr)
            self.assertNotIn("app.py", search.stdout)
            conn = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                row = conn.execute("SELECT hash FROM file_index_state WHERE path = 'app.py'").fetchone()
                chunk_count = conn.execute("SELECT count(*) FROM chunks_fts WHERE path = 'app.py'").fetchone()[0]
            finally:
                conn.close()
            self.assertIsNone(row)
            self.assertEqual(chunk_count, 0)

    def test_audit_secrets_optimize_and_mcp_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root)
            (root / "config.py").write_text(
                "pass" + "word = \"not-a-real-value-for-scanner\"\n",
                encoding="utf-8",
            )

            audit = subprocess.run(
                [str(root / "pmem"), "audit", "--secrets"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(audit.returncode, 1, audit.stderr)
            self.assertIn("possible_secret", audit.stdout)
            self.assertIn("config.py:1", audit.stdout)
            self.assertNotIn("not-a-real-value-for-scanner", audit.stdout)

            optimize = subprocess.run(
                [str(root / "pmem"), "optimize"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(optimize.returncode, 0, optimize.stderr)
            self.assertIn("Memory Optimize", optimize.stdout)

            mcp_config = subprocess.run(
                [str(root / "pmem"), "mcp-config"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(mcp_config.returncode, 0, mcp_config.stderr)
            self.assertIn("[mcp_servers.project_memory]", mcp_config.stdout)
            self.assertIn(str(root / "pmem"), mcp_config.stdout)

            write_mcp = subprocess.run(
                [str(root / "pmem"), "mcp-config", "--client", "claude", "--write"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(write_mcp.returncode, 0, write_mcp.stderr)
            mcp_json = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
            self.assertIn("project_memory", mcp_json["mcpServers"])

    def test_secret_allowlist_entropy_watch_loop_and_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root, agent="multiagent")
            (root / "token.txt").write_text(
                'client_secret = "aZ9qLm82Pq7Vr4St1Nx6Yp3Kd8Qw5Er2"\n',
                encoding="utf-8",
            )
            audit = subprocess.run(
                [str(root / "pmem"), "audit", "--secrets"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(audit.returncode, 1, audit.stderr)
            self.assertIn("high_entropy_secret", audit.stdout)
            fingerprint = audit.stdout.rsplit(" ", 1)[-1].strip()

            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8") + f"\naudit:\n  secrets:\n    allowlist:\n      - {fingerprint}\n",
                encoding="utf-8",
            )
            allowed = subprocess.run(
                [str(root / "pmem"), "audit", "--secrets"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(allowed.returncode, 0, allowed.stderr)

            task = root / ".agents/tasks/frontend-review.md"
            task.write_text(
                "# Review header / Проверка\n\nType: handoff\nStatus: active\nRole: reviewer\n",
                encoding="utf-8",
            )
            tasks = subprocess.run(
                [str(root / "pmem"), "tasks", "check", "--role", "reviewer"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(tasks.returncode, 0, tasks.stderr)
            self.assertIn("Review header", tasks.stdout)
            self.assertNotIn("Agent Tasks", tasks.stdout)

            watch = subprocess.run(
                [str(root / "pmem"), "watch", "--interval", "0", "--max-runs", "1"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(watch.returncode, 0, watch.stderr)
            self.assertIn("watch check", watch.stdout)

    def test_tasks_close_updates_markdown_and_indexes_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root, agent="multiagent")
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )
            task = root / ".agents/tasks/frontend-review.md"
            task.write_text(
                "# Review Product Card\n\nType: handoff\nStatus: active\nRole: reviewer\n",
                encoding="utf-8",
            )

            close = subprocess.run(
                [
                    str(root / "pmem"),
                    "tasks",
                    "close",
                    "--file",
                    ".agents/tasks/frontend-review.md",
                    "--summary",
                    "Reviewed product card dependencies",
                    "--command",
                    "npm test",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(close.returncode, 0, close.stderr)
            self.assertIn("task closed", close.stdout)
            text = task.read_text(encoding="utf-8")
            self.assertIn("Status: done", text)
            self.assertIn("## Completion", text)
            self.assertIn("Reviewed product card dependencies", text)

            active = subprocess.run(
                [str(root / "pmem"), "tasks", "check"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(active.returncode, 0, active.stderr)
            self.assertIn("Tasks: none", active.stdout)

            all_tasks = subprocess.run(
                [str(root / "pmem"), "tasks", "list", "--all"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(all_tasks.returncode, 0, all_tasks.stderr)
            self.assertIn("[done]", all_tasks.stdout)
            self.assertIn("Review Product Card", all_tasks.stdout)

            conn = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                row = conn.execute(
                    "SELECT hash FROM file_index_state WHERE path = '.agents/tasks/frontend-review.md'"
                ).fetchone()
            finally:
                conn.close()
            self.assertIsNotNone(row)

    def test_tasks_linear_bridge_exports_imports_and_indexes_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root, agent="multiagent")
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )
            task = root / ".agents/tasks/frontend-review.md"
            task.write_text(
                "# Review Product Card\n\nType: handoff\nStatus: active\nRole: reviewer\n",
                encoding="utf-8",
            )

            status = subprocess.run(
                [str(root / "pmem"), "tasks", "linear", "status"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("Linear bridge", status.stdout)
            self.assertIn("config: disabled", status.stdout)
            self.assertIn("local_tasks: 1", status.stdout)

            export_path = root / ".project-memory/linear/tasks-export.json"
            exported = subprocess.run(
                [str(root / "pmem"), "tasks", "linear", "export", "--out", str(export_path)],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(exported.returncode, 0, exported.stderr)
            self.assertIn("Linear export", exported.stdout)
            export_data = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertEqual(export_data["schema"], "pmem-linear-bridge-v1")
            self.assertEqual(export_data["tasks"][0]["path"], ".agents/tasks/frontend-review.md")

            import_path = root / ".project-memory/linear/issues.json"
            import_path.write_text(
                json.dumps(
                    {
                        "issues": [
                            {
                                "identifier": "LIN-1",
                                "title": "Imported Linear Task",
                                "state": "open",
                                "role": "reviewer",
                                "url": "https://linear.app/example/issue/LIN-1",
                                "description": "Review imported task before frontend work.",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            imported = subprocess.run(
                [str(root / "pmem"), "tasks", "linear", "import", "--file", str(import_path)],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(imported.returncode, 0, imported.stderr)
            self.assertIn("Linear import", imported.stdout)
            imported_task = root / ".agents/tasks/linear/lin-1-imported-linear-task.md"
            self.assertTrue(imported_task.exists())
            self.assertIn("Linear ID: LIN-1", imported_task.read_text(encoding="utf-8"))

            tasks = subprocess.run(
                [str(root / "pmem"), "tasks", "check", "--role", "reviewer"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(tasks.returncode, 0, tasks.stderr)
            self.assertIn("Imported Linear Task", tasks.stdout)

            conn = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                row = conn.execute(
                    "SELECT hash FROM file_index_state WHERE path = '.agents/tasks/linear/lin-1-imported-linear-task.md'"
                ).fetchone()
            finally:
                conn.close()
            self.assertIsNotNone(row)

    def test_modules_command_enables_optional_human_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root)

            before = subprocess.run(
                [str(root / "pmem"), "modules", "list"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(before.returncode, 0, before.stderr)
            self.assertIn("human: disabled", before.stdout)
            self.assertFalse((root / ".project-memory/human").exists())

            enable = subprocess.run(
                [str(root / "pmem"), "modules", "set", "human", "--enabled", "true"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(enable.returncode, 0, enable.stderr)
            self.assertIn("human: enabled", enable.stdout)
            self.assertTrue((root / ".project-memory/human").exists())
            self.assertIn("enabled: true", (root / ".project-memory/config.yaml").read_text(encoding="utf-8"))

            disable = subprocess.run(
                [str(root / "pmem"), "modules", "set", "human", "--enabled", "false"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(disable.returncode, 0, disable.stderr)
            self.assertIn("human: disabled", disable.stdout)
            self.assertTrue((root / ".project-memory/human").exists())

    def test_human_layer_exports_cleans_and_searches_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )
            notes = root / "notes"
            notes.mkdir()
            source = notes / "seo.md"
            source.write_text("# SEO Rules\n\nUse canonical-human-token for product pages.\n", encoding="utf-8")

            add = subprocess.run(
                [
                    str(root / "pmem"),
                    "knowledge",
                    "add",
                    "--type",
                    "seo",
                    "--title",
                    "SEO Rules",
                    "--file",
                    "notes/seo.md",
                    "--tags",
                    "seo,human",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(add.returncode, 0, add.stderr)

            disabled_export = subprocess.run(
                [str(root / "pmem"), "human", "export"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(disabled_export.returncode, 2)
            self.assertIn("human module is disabled", disabled_export.stderr)

            enable = subprocess.run(
                [str(root / "pmem"), "modules", "set", "human", "--enabled", "true"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(enable.returncode, 0, enable.stderr)

            stale = root / ".project-memory/human/knowledge/stale.md"
            stale.parent.mkdir(parents=True, exist_ok=True)
            stale.write_text("# stale\n", encoding="utf-8")
            export = subprocess.run(
                [str(root / "pmem"), "human", "export"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(export.returncode, 0, export.stderr)
            self.assertIn("Human export", export.stdout)
            self.assertFalse(stale.exists())
            human_note = root / ".project-memory/human/knowledge/seo-rules.md"
            self.assertTrue(human_note.exists())
            human_text = human_note.read_text(encoding="utf-8")
            self.assertIn("source_layer: \"knowledge\"", human_text)
            self.assertIn("[[knowledge:seo-rules]]", human_text)

            search = subprocess.run(
                [str(root / "pmem"), "human", "search", "--query", "canonical human token"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(search.returncode, 0, search.stderr)
            self.assertIn(".project-memory/human/knowledge/seo-rules.md", search.stdout)

            global_search = subprocess.run(
                [str(root / "pmem"), "search", "--query", "canonical human token", "--layer", "human"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(global_search.returncode, 0, global_search.stderr)
            self.assertIn(".project-memory/human/knowledge/seo-rules.md", global_search.stdout)

            conn = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                row = conn.execute(
                    "SELECT count(*) FROM nodes WHERE layer = 'human' AND kind = 'HumanChunk'"
                ).fetchone()
            finally:
                conn.close()
            self.assertGreater(row[0], 0)

    def test_human_sync_updates_edited_knowledge_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )
            notes = root / "notes"
            notes.mkdir()
            source = notes / "seo.md"
            source.write_text("# SEO Rules\n\nUse initial-human-sync-token.\n", encoding="utf-8")
            subprocess.run(
                [
                    str(root / "pmem"),
                    "knowledge",
                    "add",
                    "--type",
                    "seo",
                    "--title",
                    "SEO Rules",
                    "--file",
                    "notes/seo.md",
                ],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                [str(root / "pmem"), "modules", "set", "human", "--enabled", "true"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                [str(root / "pmem"), "human", "export"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            human_note = root / ".project-memory/human/knowledge/seo-rules.md"
            human_text = human_note.read_text(encoding="utf-8")
            human_note.write_text(
                human_text.replace("Use initial-human-sync-token.", "Use edited-human-sync-token."),
                encoding="utf-8",
            )
            sync = subprocess.run(
                [str(root / "pmem"), "human", "sync"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(sync.returncode, 0, sync.stderr)
            self.assertIn("synced: 1", sync.stdout)

            show = subprocess.run(
                [str(root / "pmem"), "knowledge", "show", "--id", "seo-rules"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(show.returncode, 0, show.stderr)
            self.assertIn("edited-human-sync-token", show.stdout)
            self.assertIn("version: 2", show.stdout)
            self.assertIn("note_body_hash:", human_note.read_text(encoding="utf-8"))

    def test_human_sync_reports_conflict_when_source_and_human_note_changed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root)
            notes = root / "notes"
            notes.mkdir()
            source = notes / "decision.md"
            source.write_text("# Storage Decision\n\nUse initial-conflict-token.\n", encoding="utf-8")
            subprocess.run(
                [
                    str(root / "pmem"),
                    "rationale",
                    "add",
                    "--type",
                    "decision",
                    "--title",
                    "Storage Decision",
                    "--file",
                    "notes/decision.md",
                    "--evidence",
                    "test evidence",
                ],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                [str(root / "pmem"), "modules", "set", "human", "--enabled", "true"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                [str(root / "pmem"), "human", "export"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            human_note = root / ".project-memory/human/rationale/storage-decision.md"
            human_note.write_text(
                human_note.read_text(encoding="utf-8").replace("initial-conflict-token", "human-conflict-token"),
                encoding="utf-8",
            )
            source.write_text("# Storage Decision\n\nUse source-conflict-token.\n", encoding="utf-8")
            subprocess.run(
                [str(root / "pmem"), "rationale", "update", "--id", "storage-decision", "--file", "notes/decision.md"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            sync = subprocess.run(
                [str(root / "pmem"), "human", "sync"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(sync.returncode, 1)
            self.assertIn("conflicts:", sync.stdout)
            self.assertIn("human note and source record both changed", sync.stdout)

            show = subprocess.run(
                [str(root / "pmem"), "rationale", "show", "--id", "storage-decision"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(show.returncode, 0, show.stderr)
            self.assertIn("source-conflict-token", show.stdout)
            self.assertNotIn("human-conflict-token", show.stdout)

    def test_human_graph_exports_mermaid_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root)
            notes = root / "notes"
            notes.mkdir()
            (notes / "knowledge.md").write_text("# Product Architecture\n\nUse local first memory.\n", encoding="utf-8")
            (notes / "rationale.md").write_text("# Use SQLite\n\nSQLite keeps the tool local.\n", encoding="utf-8")

            rationale = subprocess.run(
                [
                    str(root / "pmem"),
                    "rationale",
                    "add",
                    "--id",
                    "use-sqlite",
                    "--title",
                    "Use SQLite",
                    "--file",
                    "notes/rationale.md",
                    "--evidence",
                    "local tests pass",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(rationale.returncode, 0, rationale.stderr)

            knowledge = subprocess.run(
                [
                    str(root / "pmem"),
                    "knowledge",
                    "add",
                    "--type",
                    "architecture",
                    "--title",
                    "Product Architecture",
                    "--file",
                    "notes/knowledge.md",
                    "--link",
                    "depends_on:rationale:use-sqlite",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(knowledge.returncode, 0, knowledge.stderr)

            subprocess.run(
                [str(root / "pmem"), "modules", "set", "human", "--enabled", "true"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                [str(root / "pmem"), "human", "export"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            graph = subprocess.run(
                [str(root / "pmem"), "human", "graph"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(graph.returncode, 0, graph.stderr)
            self.assertIn("Human graph", graph.stdout)

            graph_json = json.loads((root / ".project-memory/human/graph.json").read_text(encoding="utf-8"))
            node_ids = {node["id"] for node in graph_json["nodes"]}
            self.assertIn("knowledge:product-architecture", node_ids)
            self.assertIn("rationale:use-sqlite", node_ids)
            self.assertIn(
                {"source": "knowledge:product-architecture", "target": "rationale:use-sqlite", "relation": "depends_on"},
                graph_json["edges"],
            )
            mermaid = (root / ".project-memory/human/graph.mmd").read_text(encoding="utf-8")
            self.assertIn("graph LR", mermaid)
            self.assertIn("depends_on", mermaid)

            graph_html = subprocess.run(
                [str(root / "pmem"), "human", "graph", "--html"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(graph_html.returncode, 0, graph_html.stderr)
            self.assertIn("Human graph HTML", graph_html.stdout)
            html = (root / ".project-memory/human/graph.html").read_text(encoding="utf-8")
            self.assertIn("Human Memory Graph", html)
            self.assertIn("layerFilter", html)
            self.assertIn("typeFilter", html)
            self.assertIn("statusFilter", html)
            self.assertIn("knowledge:product-architecture", html)

    def test_mcp_human_tools_export_search_and_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )
            notes = root / "notes"
            notes.mkdir()
            (notes / "research.md").write_text("# Human Research\n\nUse mcp-human-token in notes.\n", encoding="utf-8")
            subprocess.run(
                [
                    str(root / "pmem"),
                    "knowledge",
                    "add",
                    "--type",
                    "research",
                    "--title",
                    "Human Research",
                    "--file",
                    "notes/research.md",
                ],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            subprocess.run(
                [str(root / "pmem"), "modules", "set", "human", "--enabled", "true"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            messages = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "unittest", "version": "0"},
                    },
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "pmem_human_export", "arguments": {}}},
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "pmem_search", "arguments": {"query": "mcp human token", "layer": "human"}},
                },
                {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "pmem_human_graph", "arguments": {}}},
            ]
            payload = "\n".join(json.dumps(message) for message in messages) + "\n"
            mcp = subprocess.run(
                [str(root / "pmem"), "mcp", "--root", str(root)],
                cwd=root,
                input=payload,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(mcp.returncode, 0, mcp.stderr)
            responses = [json.loads(line) for line in mcp.stdout.splitlines()]
            by_id = {item["id"]: item for item in responses}
            tool_names = {tool["name"] for tool in by_id[2]["result"]["tools"]}
            self.assertIn("pmem_human_export", tool_names)
            self.assertIn("pmem_human_search", tool_names)
            self.assertIn("pmem_human_graph", tool_names)
            self.assertIn("generated", by_id[3]["result"]["structuredContent"]["human"])
            self.assertIn(".project-memory/human/knowledge/human-research.md", by_id[4]["result"]["content"][0]["text"])
            self.assertTrue((root / ".project-memory/human/graph.json").exists())
            self.assertIn("nodes", by_id[5]["result"]["structuredContent"]["human_graph"])

    def test_context_and_search_work_after_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root)
            (root / "app.py").write_text("def pay(amount):\n    return amount > 0\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py"], cwd=root)
            subprocess.run(["git", "commit", "-m", "init"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )

            (root / "app.py").write_text("def pay(amount):\n    return amount >= 0\n", encoding="utf-8")
            subprocess.run(
                [str(root / "pmem"), "index", "--mode", "full"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            context = subprocess.run(
                [
                    str(root / "pmem"),
                    "context",
                    "--task",
                    "change payment validation",
                    "--base",
                    "HEAD",
                    "--out",
                    ".project-memory/reports/CHANGE_CONTEXT.md",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
            )
            self.assertEqual(context.returncode, 0, context.stdout)
            content = (root / ".project-memory/reports/CHANGE_CONTEXT.md").read_text(encoding="utf-8")
            self.assertIn("# Change Context", content)
            self.assertIn("## Agent Checklist", content)

            search = subprocess.run(
                [str(root / "pmem"), "search", "--query", "pay amount", "--limit", "5"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(search.returncode, 0, search.stderr)
            self.assertIn("app.py", search.stdout)

    def test_mcp_stdio_lists_tools_and_calls_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root)
            (root / "app.py").write_text("def pay(amount):\n    return amount > 0\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py"], cwd=root)
            subprocess.run(["git", "commit", "-m", "init"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )
            subprocess.run(
                [str(root / "pmem"), "index", "--mode", "full"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            messages = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "unittest", "version": "0"},
                    },
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "pmem_search",
                        "arguments": {"query": "pay amount", "limit": 5},
                    },
                },
            ]
            payload = "\n".join(json.dumps(message) for message in messages) + "\n"
            mcp = subprocess.run(
                [str(root / "pmem"), "mcp", "--root", str(root)],
                cwd=root,
                input=payload,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(mcp.returncode, 0, mcp.stderr)
            responses = [json.loads(line) for line in mcp.stdout.splitlines()]
            by_id = {item["id"]: item for item in responses}

            self.assertEqual(by_id[1]["result"]["protocolVersion"], "2025-06-18")
            tool_names = {tool["name"] for tool in by_id[2]["result"]["tools"]}
            self.assertIn("pmem_context", tool_names)
            self.assertIn("pmem_search", tool_names)
            self.assertIn("pmem_record_failure", tool_names)
            self.assertIn("pmem_status", tool_names)
            self.assertIn("pmem_search_debug", tool_names)
            self.assertIn("pmem_eval", tool_names)
            self.assertIn("pmem_audit", tool_names)
            self.assertIn("pmem_modules", tool_names)
            self.assertIn("pmem_watch_status", tool_names)
            self.assertIn("app.py", by_id[3]["result"]["content"][0]["text"])
            self.assertIn("results", by_id[3]["result"]["structuredContent"])

    def test_mcp_task_write_tools_create_assign_and_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_project(root, agent="multiagent")

            messages = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "unittest", "version": "0"},
                    },
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "pmem_tasks_create",
                        "arguments": {
                            "title": "Build payment form",
                            "russian_subtitle": "Форма оплаты",
                            "type": "handoff",
                            "role": "frontend",
                            "goal": "Implement the payment form UI.",
                            "context": "Use project UI rules.",
                            "evidence": ["docs/ui.md", "pmem_context:payment"],
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "pmem_tasks_assign",
                        "arguments": {
                            "file": ".agents/tasks/build-payment-form.md",
                            "role": "reviewer",
                            "summary": "Needs review after implementation.",
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "pmem_tasks_close",
                        "arguments": {
                            "file": ".agents/tasks/build-payment-form.md",
                            "summary": "Reviewed and closed.",
                            "command": "./pmem tasks check",
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {"name": "pmem_tasks", "arguments": {"all": True}},
                },
            ]
            payload = "\n".join(json.dumps(message) for message in messages) + "\n"
            mcp = subprocess.run(
                [str(root / "pmem"), "mcp", "--root", str(root)],
                cwd=root,
                input=payload,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(mcp.returncode, 0, mcp.stderr)
            responses = [json.loads(line) for line in mcp.stdout.splitlines()]
            by_id = {item["id"]: item for item in responses}
            tools = {tool["name"]: tool for tool in by_id[2]["result"]["tools"]}
            for name in ["pmem_tasks_create", "pmem_tasks_assign", "pmem_tasks_close"]:
                self.assertIn(name, tools)
                self.assertFalse(tools[name]["annotations"]["readOnlyHint"])

            self.assertEqual(by_id[3]["result"]["structuredContent"]["task"]["path"], ".agents/tasks/build-payment-form.md")
            self.assertEqual(by_id[4]["result"]["structuredContent"]["task"]["role"], "reviewer")
            self.assertEqual(by_id[5]["result"]["structuredContent"]["task"]["status"], "done")
            self.assertIn("Build payment form", by_id[6]["result"]["content"][0]["text"])
            task_text = (root / ".agents/tasks/build-payment-form.md").read_text(encoding="utf-8")
            self.assertIn("# Build payment form / Форма оплаты", task_text)
            self.assertIn("Role: reviewer", task_text)
            self.assertIn("Summary: Reviewed and closed.", task_text)

    def test_knowledge_lifecycle_updates_current_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes = root / "notes"
            notes.mkdir()
            source = notes / "seo.md"
            source.write_text(
                "# Product Page SEO\n\nUse legacy-copy-token for product pages.\n",
                encoding="utf-8",
            )
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )

            add = subprocess.run(
                [
                    str(root / "pmem"),
                    "knowledge",
                    "add",
                    "--type",
                    "seo",
                    "--title",
                    "Product Page SEO",
                    "--file",
                    "notes/seo.md",
                    "--tags",
                    "seo,content",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(add.returncode, 0, add.stderr)
            self.assertIn("product-page-seo", add.stdout)
            self.assertTrue((root / ".project-memory/knowledge/seo/product-page-seo.md").exists())

            search = subprocess.run(
                [str(root / "pmem"), "knowledge", "search", "--query", "legacy-copy-token"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(search.returncode, 0, search.stderr)
            self.assertIn("Product Page SEO", search.stdout)

            source.write_text(
                "# Product Page SEO\n\nUse canonical-copy-token for product pages.\n",
                encoding="utf-8",
            )
            update = subprocess.run(
                [
                    str(root / "pmem"),
                    "knowledge",
                    "update",
                    "--id",
                    "product-page-seo",
                    "--file",
                    "notes/seo.md",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(update.returncode, 0, update.stderr)
            self.assertIn("v2", update.stdout)

            old_search = subprocess.run(
                [str(root / "pmem"), "knowledge", "search", "--query", "legacy-copy-token"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(old_search.returncode, 0, old_search.stderr)
            self.assertNotIn("legacy-copy-token", old_search.stdout)

            new_search = subprocess.run(
                [str(root / "pmem"), "search", "--query", "canonical-copy-token", "--layer", "knowledge"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(new_search.returncode, 0, new_search.stderr)
            self.assertIn("Product Page SEO", new_search.stdout)
            self.assertIn("canonical", new_search.stdout)

            context = subprocess.run(
                [
                    str(root / "pmem"),
                    "knowledge",
                    "context",
                    "--task",
                    "rewrite product page seo copy",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(context.returncode, 0, context.stderr)
            self.assertIn("## Current Knowledge", context.stdout)
            self.assertIn("product-page-seo", context.stdout)

            show = subprocess.run(
                [str(root / "pmem"), "knowledge", "show", "--id", "product-page-seo"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(show.returncode, 0, show.stderr)
            self.assertIn("version: 2", show.stdout)
            self.assertNotIn("version: 1", show.stdout)

            retire = subprocess.run(
                [str(root / "pmem"), "knowledge", "retire", "--id", "product-page-seo"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(retire.returncode, 0, retire.stderr)
            self.assertIn("archived", retire.stdout)

            retired_search = subprocess.run(
                [str(root / "pmem"), "knowledge", "search", "--query", "canonical-copy-token"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(retired_search.returncode, 0, retired_search.stderr)
            self.assertEqual(retired_search.stdout.strip(), "")

            conn = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                row = conn.execute(
                    "SELECT status, version FROM knowledge_entries WHERE id = 'product-page-seo'"
                ).fetchone()
            finally:
                conn.close()
            self.assertEqual(row, ("archived", 2))

    def test_rationale_lifecycle_and_reset_task_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes = root / "notes"
            notes.mkdir()
            source = notes / "storage.md"
            source.write_text(
                "# Storage Decision\n\nUse legacy-db-token as the source of truth.\n",
                encoding="utf-8",
            )
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )

            add = subprocess.run(
                [
                    str(root / "pmem"),
                    "rationale",
                    "add",
                    "--type",
                    "decision",
                    "--title",
                    "Storage Decision",
                    "--file",
                    "notes/storage.md",
                    "--why",
                    "local-first storage",
                    "--rejected",
                    "Remote database: unnecessary for local project memory",
                    "--evidence",
                    "doctor: sqlite ok",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(add.returncode, 0, add.stderr)
            self.assertIn("storage-decision", add.stdout)
            self.assertTrue((root / ".project-memory/rationale/decision/storage-decision.md").exists())

            search = subprocess.run(
                [str(root / "pmem"), "rationale", "search", "--query", "why remote database"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(search.returncode, 0, search.stderr)
            self.assertIn("Storage Decision", search.stdout)
            self.assertIn("[hybrid", search.stdout)

            source.write_text(
                "# Storage Decision\n\nUse canonical-db-token as the source of truth.\n",
                encoding="utf-8",
            )
            update = subprocess.run(
                [
                    str(root / "pmem"),
                    "rationale",
                    "update",
                    "--id",
                    "storage-decision",
                    "--file",
                    "notes/storage.md",
                    "--why",
                    "SQLite is local-first and upgrade-safe",
                    "--evidence",
                    "tests: upgrade preserves graph.sqlite",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(update.returncode, 0, update.stderr)
            self.assertIn("v2", update.stdout)

            old_search = subprocess.run(
                [str(root / "pmem"), "rationale", "search", "--query", "legacy-db-token"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(old_search.returncode, 0, old_search.stderr)
            self.assertNotIn("legacy-db-token", old_search.stdout)

            layer_search = subprocess.run(
                [str(root / "pmem"), "search", "--query", "canonical db storage", "--layer", "rationale"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(layer_search.returncode, 0, layer_search.stderr)
            self.assertIn("rationale:storage-decision", layer_search.stdout)
            self.assertIn("[hybrid", layer_search.stdout)

            context = subprocess.run(
                [
                    str(root / "pmem"),
                    "context",
                    "--task",
                    "change memory storage",
                    "--reset-task",
                    "--out",
                    ".project-memory/reports/CHANGE_CONTEXT.md",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(context.returncode, 0, context.stderr)
            report = (root / ".project-memory/reports/CHANGE_CONTEXT.md").read_text(encoding="utf-8")
            self.assertIn("## Task Boundary", report)
            self.assertIn("## Retrieved Rationale", report)
            self.assertIn("storage-decision", report)

            show = subprocess.run(
                [str(root / "pmem"), "rationale", "show", "--id", "storage-decision"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(show.returncode, 0, show.stderr)
            self.assertIn("version: 2", show.stdout)
            self.assertNotIn("version: 1", show.stdout)

            retire = subprocess.run(
                [str(root / "pmem"), "rationale", "retire", "--id", "storage-decision"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(retire.returncode, 0, retire.stderr)
            self.assertIn("archived", retire.stdout)

            retired_search = subprocess.run(
                [str(root / "pmem"), "rationale", "search", "--query", "canonical-db-token"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(retired_search.returncode, 0, retired_search.stderr)
            self.assertEqual(retired_search.stdout.strip(), "")

            conn = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                row = conn.execute(
                    "SELECT status, version FROM rationale_entries WHERE id = 'storage-decision'"
                ).fetchone()
            finally:
                conn.close()
            self.assertEqual(row, ("archived", 2))

    def test_indexes_js_ts_import_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            component_dir = root / "src" / "components"
            app_dir = root / "src" / "app"
            component_dir.mkdir(parents=True)
            app_dir.mkdir(parents=True)
            (root / "tsconfig.json").write_text(
                '{"compilerOptions":{"baseUrl":".","paths":{"@/*":["src/*"]}}}',
                encoding="utf-8",
            )
            (root / "package.json").write_text(
                '{"scripts":{"test":"vitest run"}}',
                encoding="utf-8",
            )
            (component_dir / "Button.tsx").write_text(
                "export const Button = ({ label }: { label: string }) => {\n"
                "  return <button>{label}</button>;\n"
                "};\n",
                encoding="utf-8",
            )
            (app_dir / "page.tsx").write_text(
                "import { Button } from '@/components/Button';\n\n"
                "export default function Page() {\n"
                "  return <Button label=\"Home\" />;\n"
                "}\n",
                encoding="utf-8",
            )
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )

            index = subprocess.run(
                [str(root / "pmem"), "index", "--mode", "full"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertIn("indexed=", index.stdout)

            conn = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                symbol_count = conn.execute(
                    "SELECT count(*) FROM nodes WHERE kind = 'Symbol' AND language = 'typescript'"
                ).fetchone()[0]
                imports = conn.execute(
                    """
                    SELECT dst.path
                    FROM edges e
                    JOIN nodes src ON src.id = e.src_id
                    JOIN nodes dst ON dst.id = e.dst_id
                    WHERE e.kind = 'IMPORTS' AND src.path = 'src/app/page.tsx'
                    """
                ).fetchall()
            finally:
                conn.close()

            self.assertGreaterEqual(symbol_count, 2)
            self.assertIn(("src/components/Button.tsx",), imports)

            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            subprocess.run(["git", "add", "src", "tsconfig.json", "package.json"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            button_path = component_dir / "Button.tsx"
            button_path.write_text(button_path.read_text(encoding="utf-8").replace("{label}", "{label.toUpperCase()}"), encoding="utf-8")

            impact = subprocess.run(
                [str(root / "pmem"), "impact", "--base", "HEAD", "--format", "markdown"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertIn("reverse import via @/components/Button", impact.stdout)
            self.assertIn("npm test", impact.stdout)

    def test_binds_js_ts_named_imports_through_barrel_exports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            component_dir = root / "src" / "components"
            app_dir = root / "src" / "app"
            component_dir.mkdir(parents=True)
            app_dir.mkdir(parents=True)
            (root / "tsconfig.json").write_text(
                '{"compilerOptions":{"baseUrl":".","paths":{"@/*":["src/*"]}}}',
                encoding="utf-8",
            )
            (component_dir / "Button.tsx").write_text(
                "export const Button = ({ label }: { label: string }) => {\n"
                "  return <button>{label}</button>;\n"
                "};\n",
                encoding="utf-8",
            )
            (component_dir / "index.ts").write_text(
                "export { Button } from './Button';\n",
                encoding="utf-8",
            )
            (app_dir / "page.tsx").write_text(
                "import { Button } from '@/components';\n\n"
                "export default function Page() {\n"
                "  return <Button label=\"Home\" />;\n"
                "}\n",
                encoding="utf-8",
            )
            install_project(root)
            config_path = root / ".project-memory/config.yaml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace("backend: auto", "backend: fallback"),
                encoding="utf-8",
            )
            subprocess.run(
                [str(root / "pmem"), "index", "--mode", "full"],
                cwd=root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            conn = sqlite3.connect(root / ".project-memory/graph.sqlite")
            try:
                rows = conn.execute(
                    """
                    SELECT src.fqn, dst.fqn, e.kind, e.confidence
                    FROM edges e
                    JOIN nodes src ON src.id = e.src_id
                    JOIN nodes dst ON dst.id = e.dst_id
                    WHERE e.source = 'binding'
                      AND src.fqn = 'src.app.page.Page'
                      AND dst.fqn = 'src.components.Button.Button'
                    ORDER BY e.kind
                    """
                ).fetchall()
            finally:
                conn.close()

            kinds = {row[2] for row in rows}
            self.assertIn("REFERENCES", kinds)
            self.assertIn("CALLS", kinds)
            self.assertTrue(all(row[3] > 0.7 for row in rows))


if __name__ == "__main__":
    unittest.main()
