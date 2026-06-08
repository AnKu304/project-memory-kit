from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from tools.project_memory.hashing import stable_id
from tools.project_memory.time_utils import utc_now

JS_TS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"}


def _language_for_path(path: str) -> str | None:
    suffix = Path(path).suffix
    if suffix == ".py":
        return "python"
    if suffix in {".ts", ".tsx", ".mts", ".cts"}:
        return "typescript"
    if suffix in JS_TS_EXTENSIONS:
        return "javascript"
    return None


class SQLiteGraphStore:
    def __init__(self, root: Path, db_path: Path):
        self.root = root
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        with self.connect() as conn:
            conn.executescript(schema)

    def node_id(self, kind: str, path: str | None = None, fqn: str | None = None, name: str | None = None) -> str:
        return stable_id("node", kind, path or "", fqn or "", name or "")

    def edge_id(self, src_id: str, dst_id: str, kind: str, source: str = "index") -> str:
        return stable_id("edge", src_id, dst_id, kind, source)

    def upsert_node(self, **fields: Any) -> str:
        now = utc_now()
        node_id = fields.get("id") or self.node_id(
            fields["kind"], fields.get("path"), fields.get("fqn"), fields.get("name")
        )
        values = {
            "id": node_id,
            "kind": fields["kind"],
            "name": fields.get("name"),
            "fqn": fields.get("fqn"),
            "path": fields.get("path"),
            "language": fields.get("language"),
            "layer": fields.get("layer"),
            "start_line": fields.get("start_line"),
            "end_line": fields.get("end_line"),
            "hash": fields.get("hash"),
            "properties_json": json.dumps(fields.get("properties") or {}, sort_keys=True),
            "created_at": fields.get("created_at") or now,
            "updated_at": now,
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO nodes (
                  id, kind, name, fqn, path, language, layer, start_line, end_line, hash,
                  properties_json, created_at, updated_at
                )
                VALUES (
                  :id, :kind, :name, :fqn, :path, :language, :layer, :start_line, :end_line,
                  :hash, :properties_json, :created_at, :updated_at
                )
                ON CONFLICT(id) DO UPDATE SET
                  kind=excluded.kind,
                  name=excluded.name,
                  fqn=excluded.fqn,
                  path=excluded.path,
                  language=excluded.language,
                  layer=excluded.layer,
                  start_line=excluded.start_line,
                  end_line=excluded.end_line,
                  hash=excluded.hash,
                  properties_json=excluded.properties_json,
                  updated_at=excluded.updated_at
                """,
                values,
            )
        return node_id

    def upsert_edge(
        self,
        src_id: str,
        dst_id: str,
        kind: str,
        source: str = "index",
        confidence: float = 1.0,
        evidence: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> str:
        edge_id = self.edge_id(src_id, dst_id, kind, source)
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO edges (
                  id, src_id, dst_id, kind, source, confidence, evidence,
                  properties_json, stale, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  confidence=excluded.confidence,
                  evidence=excluded.evidence,
                  properties_json=excluded.properties_json,
                  stale=0,
                  updated_at=excluded.updated_at
                """,
                (
                    edge_id,
                    src_id,
                    dst_id,
                    kind,
                    source,
                    confidence,
                    evidence,
                    json.dumps(properties or {}, sort_keys=True),
                    now,
                    now,
                ),
            )
        return edge_id

    def clear_generated_file_memory(self, path: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM chunks_fts WHERE path = ?", (path,))
            conn.execute("DELETE FROM nodes WHERE kind IN ('Symbol', 'Chunk') AND path = ?", (path,))
            conn.execute("DELETE FROM file_index_state WHERE path = ?", (path,))

    def clear_removed_file_memory(self, path: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM chunks_fts WHERE path = ?", (path,))
            conn.execute("DELETE FROM nodes WHERE path = ?", (path,))
            conn.execute("DELETE FROM file_index_state WHERE path = ?", (path,))

    def indexed_file_paths(self) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT path FROM file_index_state").fetchall()
        return {str(row["path"]) for row in rows}

    def update_file_state(self, path: str, file_hash: str, parser: str, warnings: list[str]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO file_index_state(path, hash, indexed_at, parser, warnings_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                  hash=excluded.hash,
                  indexed_at=excluded.indexed_at,
                  parser=excluded.parser,
                  warnings_json=excluded.warnings_json
                """,
                (path, file_hash, utc_now(), parser, json.dumps(warnings)),
            )

    def file_hash(self, path: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT hash FROM file_index_state WHERE path = ?", (path,)).fetchone()
        return row["hash"] if row else None

    def upsert_chunk(self, path: str, fqn: str | None, start_line: int, end_line: int, content: str) -> str:
        chunk_id = self.upsert_node(
            kind="Chunk",
            name=fqn or path,
            fqn=f"{path}:{start_line}-{end_line}",
            path=path,
            language=_language_for_path(path),
            start_line=start_line,
            end_line=end_line,
            properties={"content": content[:2000]},
        )
        with self.connect() as conn:
            conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
            conn.execute(
                "INSERT INTO chunks_fts(chunk_id, path, fqn, content) VALUES (?, ?, ?, ?)",
                (chunk_id, path, fqn or "", content),
            )
        return chunk_id

    def query(self, sql: str, args: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute(sql, args).fetchall())
