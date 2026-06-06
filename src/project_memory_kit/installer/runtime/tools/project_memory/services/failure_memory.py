from __future__ import annotations

import json
import re
from pathlib import Path

from tools.project_memory.config import config_path
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.hashing import stable_id
from tools.project_memory.time_utils import utc_now


TRACE_RE = re.compile(r'File "([^"]+)", line (\d+), in ([^\n]+)')
ERROR_RE = re.compile(r"([A-Z][A-Za-z0-9_]*Error|Exception):\s*(.+)")


def normalize_message(message: str) -> str:
    message = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", message)
    message = re.sub(r"\d+", "N", message)
    return message.strip()


def record_failure(root: Path, command: str, log_file: Path) -> str:
    text = log_file.read_text(encoding="utf-8", errors="replace")
    frames = TRACE_RE.findall(text)
    error_match = ERROR_RE.search(text)
    error_kind = error_match.group(1) if error_match else "UnknownError"
    message = error_match.group(2) if error_match else text.splitlines()[-1] if text.splitlines() else ""
    normalized = normalize_message(message)
    top_frame = ""
    for filename, line, func in reversed(frames):
        if str(root) in filename or not filename.startswith("/"):
            top_frame = f"{filename}:{line}:{func.strip()}"
            break
    fingerprint = stable_id(error_kind, normalized, top_frame)
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    now = utc_now()
    command_id = store.upsert_node(kind="Command", name=command, fqn=command, properties={"log_file": str(log_file)})
    failure_id = store.upsert_node(
        kind="Failure",
        name=error_kind,
        fqn=fingerprint,
        properties={"normalized_message": normalized, "top_project_frame": top_frame},
    )
    store.upsert_edge(command_id, failure_id, "OCCURRED_IN", evidence=str(log_file))
    with store.connect() as conn:
        existing = conn.execute(
            "SELECT count FROM failure_fingerprints WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE failure_fingerprints
                SET last_seen_at = ?, count = count + 1, properties_json = ?
                WHERE fingerprint = ?
                """,
                (now, json.dumps({"log_file": str(log_file)}, sort_keys=True), fingerprint),
            )
        else:
            conn.execute(
                """
                INSERT INTO failure_fingerprints(
                  fingerprint, error_kind, normalized_message, top_project_frame,
                  first_seen_at, last_seen_at, count, properties_json
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    fingerprint,
                    error_kind,
                    normalized,
                    top_frame,
                    now,
                    now,
                    json.dumps({"log_file": str(log_file)}, sort_keys=True),
                ),
            )
    return fingerprint

