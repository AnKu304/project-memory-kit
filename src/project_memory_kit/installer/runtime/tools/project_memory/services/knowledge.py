from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from tools.project_memory.config import config_path, load_config
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.hashing import sha256_text, stable_id
from tools.project_memory.services.search import search as global_search
from tools.project_memory.time_utils import utc_now
from tools.project_memory.vector.qdrant_store import QdrantLocalStore

CURRENT = "current"
SUPERSEDED = "superseded"
ARCHIVED = "archived"
VALID_STATUSES = {CURRENT, SUPERSEDED, ARCHIVED}


@dataclass(frozen=True)
class KnowledgeResult:
    id: str
    type: str
    title: str
    status: str
    version: int
    path: str


def _store(root: Path) -> SQLiteGraphStore:
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    return store


def _knowledge_dir(root: Path) -> Path:
    return config_path(root, "knowledge_dir")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return slug or stable_id("knowledge", value)


def _normalize_type(value: str) -> str:
    return _slugify(value or "note")


def _normalize_status(value: str) -> str:
    status = (value or CURRENT).strip().lower()
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid knowledge status: {value}")
    return status


def _tags(values: Iterable[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        for item in str(value).split(","):
            tag = item.strip()
            if tag and tag not in result:
                result.append(tag)
    return result


def _source_path(root: Path, file_path: str | Path) -> Path:
    path = Path(file_path)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _read_source(root: Path, file_path: str | Path) -> str:
    path = _source_path(root, file_path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    return path.read_text(encoding="utf-8")


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _entry_path(root: Path, item_type: str, entry_id: str) -> Path:
    return _knowledge_dir(root) / item_type / f"{entry_id}.md"


def _summary_for(content: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit.strip()
    for line in _strip_frontmatter(content).splitlines():
        clean = line.strip().lstrip("#").strip()
        if clean:
            return clean[:320]
    return ""


def _frontmatter(
    entry_id: str,
    item_type: str,
    title: str,
    status: str,
    version: int,
    source: str | None,
    tags: list[str],
    supersedes: str | None,
) -> str:
    lines = [
        "---",
        f"pmem_id: {entry_id}",
        f"type: {item_type}",
        f"title: {title}",
        f"status: {status}",
        f"version: {version}",
    ]
    if source:
        lines.append(f"source: {source}")
    if tags:
        lines.append("tags:")
        lines.extend(f"  - {tag}" for tag in tags)
    if supersedes:
        lines.append(f"supersedes: {supersedes}")
    lines.extend(["---", ""])
    return "\n".join(lines)


def _render_markdown(
    entry_id: str,
    item_type: str,
    title: str,
    status: str,
    version: int,
    source: str | None,
    tags: list[str],
    supersedes: str | None,
    content: str,
) -> str:
    body = _strip_frontmatter(content).strip() + "\n"
    return _frontmatter(entry_id, item_type, title, status, version, source, tags, supersedes) + body


def _strip_frontmatter(content: str) -> str:
    if not content.startswith("---\n"):
        return content
    marker = content.find("\n---", 4)
    if marker == -1:
        return content
    end = content.find("\n", marker + 4)
    if end == -1:
        return ""
    return content[end + 1 :]


def _entry_row(store: SQLiteGraphStore, entry_id: str) -> sqlite3.Row | None:
    rows = store.query("SELECT * FROM knowledge_entries WHERE id = ?", (entry_id,))
    return rows[0] if rows else None


def _clear_entry_chunks(store: SQLiteGraphStore, path: str) -> None:
    with store.connect() as conn:
        chunk_ids = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM nodes WHERE kind = 'KnowledgeChunk' AND path = ?",
                (path,),
            ).fetchall()
        ]
        if chunk_ids:
            placeholders = ",".join("?" for _ in chunk_ids)
            conn.execute(f"DELETE FROM chunks_fts WHERE chunk_id IN ({placeholders})", tuple(chunk_ids))
            conn.execute(f"DELETE FROM nodes WHERE id IN ({placeholders})", tuple(chunk_ids))


def _chunks(content: str, max_chars: int = 1800) -> list[str]:
    blocks = re.split(r"\n(?=#{1,6}\s)|\n\s*\n", content.strip())
    chunks: list[str] = []
    current = ""
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        next_value = f"{current}\n\n{block}".strip() if current else block
        if len(next_value) <= max_chars:
            current = next_value
            continue
        if current:
            chunks.append(current)
        while len(block) > max_chars:
            chunks.append(block[:max_chars].strip())
            block = block[max_chars - 120 :].strip()
        current = block
    if current:
        chunks.append(current)
    return chunks or [content[:max_chars]]


def _vectors(root: Path) -> QdrantLocalStore:
    cfg = load_config(root)
    vector_cfg = cfg.get("vector", {})
    return QdrantLocalStore(
        config_path(root, "qdrant_path"),
        cfg.get("memory", {}).get("vector_size", 64),
        backend=vector_cfg.get("backend", "auto"),
        collection=vector_cfg.get("collection", "project_memory_chunks"),
        model_name=vector_cfg.get("embedding_model"),
        url=vector_cfg.get("url"),
        root=root,
    )


def _index_entry(
    root: Path,
    store: SQLiteGraphStore,
    entry_id: str,
    item_type: str,
    title: str,
    status: str,
    version: int,
    path: str,
    summary: str,
    content: str,
    tags: list[str],
) -> None:
    _clear_entry_chunks(store, path)
    knowledge_id = store.upsert_node(
        kind="Knowledge",
        name=title,
        fqn=entry_id,
        path=path,
        language="markdown",
        layer="knowledge",
        properties={
            "type": item_type,
            "status": status,
            "version": version,
            "summary": summary,
            "tags": tags,
        },
    )
    if status != CURRENT:
        return

    vectors = _vectors(root)
    try:
        for index, chunk in enumerate(_chunks(content), start=1):
            chunk_id = store.upsert_node(
                id=stable_id("knowledge-chunk", entry_id, index),
                kind="KnowledgeChunk",
                name=f"{title} chunk {index}",
                fqn=f"knowledge:{entry_id}#chunk-{index}",
                path=path,
                language="markdown",
                layer="knowledge",
                properties={
                    "content": chunk[:2000],
                    "knowledge_id": entry_id,
                    "type": item_type,
                    "status": status,
                    "version": version,
                    "summary": summary,
                    "tags": tags,
                },
            )
            store.upsert_edge(knowledge_id, chunk_id, "CONTAINS", source="knowledge", confidence=1.0)
            with store.connect() as conn:
                conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
                conn.execute(
                    "INSERT INTO chunks_fts(chunk_id, path, fqn, content) VALUES (?, ?, ?, ?)",
                    (chunk_id, path, f"knowledge:{entry_id}", f"{title}\n{summary}\n{chunk}"),
                )
            vectors.upsert_chunk(
                chunk_id,
                f"{title}\n{summary}\n{chunk}",
                {
                    "chunk_id": chunk_id,
                    "node_id": chunk_id,
                    "file_path": path,
                    "knowledge_id": entry_id,
                    "knowledge_type": item_type,
                    "title": title,
                    "status": status,
                    "version": version,
                    "kind": "knowledge",
                    "hash": sha256_text(content),
                },
            )
    finally:
        vectors.close()


def _save_links(store: SQLiteGraphStore, entry_id: str, links: Iterable[str]) -> None:
    now = utc_now()
    with store.connect() as conn:
        conn.execute("DELETE FROM knowledge_links WHERE knowledge_id = ?", (entry_id,))
        for raw in links:
            value = str(raw).strip()
            if not value:
                continue
            relation, _, target = value.partition(":")
            if not target:
                relation, target = "relates_to", relation
            link_id = stable_id("knowledge-link", entry_id, relation, target)
            conn.execute(
                """
                INSERT INTO knowledge_links(id, knowledge_id, relation, target, properties_json, created_at)
                VALUES (?, ?, ?, ?, '{}', ?)
                ON CONFLICT(id) DO UPDATE SET relation=excluded.relation, target=excluded.target
                """,
                (link_id, entry_id, relation, target, now),
            )


def add_knowledge(
    root: Path,
    item_type: str,
    title: str,
    file_path: str | Path,
    entry_id: str | None = None,
    tags: Iterable[str] | None = None,
    source: str | None = None,
    summary: str | None = None,
    supersedes: str | None = None,
    links: Iterable[str] | None = None,
) -> KnowledgeResult:
    store = _store(root)
    item_type = _normalize_type(item_type)
    entry_id = _slugify(entry_id or title)
    if _entry_row(store, entry_id):
        raise ValueError(f"knowledge entry already exists: {entry_id}")
    if supersedes and not _entry_row(store, _slugify(supersedes)):
        raise ValueError(f"superseded knowledge entry not found: {supersedes}")

    content = _read_source(root, file_path)
    tag_list = _tags(tags)
    status = CURRENT
    version = 1
    summary_value = _summary_for(content, summary)
    path = _entry_path(root, item_type, entry_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = _render_markdown(entry_id, item_type, title, status, version, source, tag_list, supersedes, content)
    path.write_text(rendered, encoding="utf-8")
    rel = _relative(root, path)
    now = utc_now()
    with store.connect() as conn:
        conn.execute(
            """
            INSERT INTO knowledge_entries(
              id, type, title, status, version, source, tags_json, path, summary,
              content_hash, supersedes, created_at, updated_at, properties_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')
            """,
            (
                entry_id,
                item_type,
                title,
                status,
                version,
                source,
                json.dumps(tag_list),
                rel,
                summary_value,
                sha256_text(rendered),
                supersedes,
                now,
                now,
            ),
        )
    _save_links(store, entry_id, links or [])
    if supersedes:
        retire_knowledge(root, supersedes, status=SUPERSEDED)
    _index_entry(root, store, entry_id, item_type, title, status, version, rel, summary_value, rendered, tag_list)
    return KnowledgeResult(entry_id, item_type, title, status, version, rel)


def update_knowledge(
    root: Path,
    entry_id: str,
    file_path: str | Path,
    title: str | None = None,
    item_type: str | None = None,
    tags: Iterable[str] | None = None,
    source: str | None = None,
    summary: str | None = None,
    links: Iterable[str] | None = None,
) -> KnowledgeResult:
    store = _store(root)
    entry_id = _slugify(entry_id)
    row = _entry_row(store, entry_id)
    if not row:
        raise ValueError(f"knowledge entry not found: {entry_id}")

    content = _read_source(root, file_path)
    next_type = _normalize_type(item_type or row["type"])
    next_title = title or row["title"]
    next_tags = _tags(tags if tags is not None else json.loads(row["tags_json"] or "[]"))
    next_source = source if source is not None else row["source"]
    version = int(row["version"]) + 1
    status = CURRENT
    summary_value = _summary_for(content, summary)
    old_path = row["path"]
    path = _entry_path(root, next_type, entry_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = _render_markdown(
        entry_id,
        next_type,
        next_title,
        status,
        version,
        next_source,
        next_tags,
        row["supersedes"],
        content,
    )
    path.write_text(rendered, encoding="utf-8")
    rel = _relative(root, path)
    if old_path != rel:
        old_full_path = root / old_path
        if old_full_path.exists():
            old_full_path.unlink()
        _clear_entry_chunks(store, old_path)
    now = utc_now()
    with store.connect() as conn:
        conn.execute(
            """
            UPDATE knowledge_entries
            SET type = ?, title = ?, status = ?, version = ?, source = ?, tags_json = ?,
                path = ?, summary = ?, content_hash = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                next_type,
                next_title,
                status,
                version,
                next_source,
                json.dumps(next_tags),
                rel,
                summary_value,
                sha256_text(rendered),
                now,
                entry_id,
            ),
        )
    if links is not None:
        _save_links(store, entry_id, links)
    _index_entry(root, store, entry_id, next_type, next_title, status, version, rel, summary_value, rendered, next_tags)
    return KnowledgeResult(entry_id, next_type, next_title, status, version, rel)


def retire_knowledge(root: Path, entry_id: str, status: str = ARCHIVED) -> KnowledgeResult:
    store = _store(root)
    entry_id = _slugify(entry_id)
    status = _normalize_status(status)
    row = _entry_row(store, entry_id)
    if not row:
        raise ValueError(f"knowledge entry not found: {entry_id}")
    now = utc_now()
    with store.connect() as conn:
        conn.execute(
            "UPDATE knowledge_entries SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, entry_id),
        )
    _clear_entry_chunks(store, row["path"])
    store.upsert_node(
        kind="Knowledge",
        name=row["title"],
        fqn=entry_id,
        path=row["path"],
        language="markdown",
        layer="knowledge",
        properties={
            "type": row["type"],
            "status": status,
            "version": int(row["version"]),
            "summary": row["summary"],
            "tags": json.loads(row["tags_json"] or "[]"),
        },
    )
    return KnowledgeResult(entry_id, row["type"], row["title"], status, int(row["version"]), row["path"])


def show_knowledge(root: Path, entry_id: str) -> str:
    store = _store(root)
    entry_id = _slugify(entry_id)
    row = _entry_row(store, entry_id)
    if not row:
        raise ValueError(f"knowledge entry not found: {entry_id}")
    path = root / row["path"]
    return path.read_text(encoding="utf-8")


def search_knowledge(root: Path, query: str, limit: int = 5, include_archived: bool = False) -> list[dict[str, object]]:
    store = _store(root)
    rows = global_search(root, query, max(limit * 4, limit), layer="knowledge")
    entry_paths = {
        str(row["path"]): row
        for row in store.query(
            "SELECT * FROM knowledge_entries WHERE status = 'current' OR ?",
            (1 if include_archived else 0,),
        )
    }
    results: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in rows:
        entry = entry_paths.get(str(item["path"]))
        if not entry:
            continue
        key = str(item["chunk_id"])
        if key in seen:
            continue
        seen.add(key)
        result = dict(item)
        result.update(
            {
                "knowledge_id": entry["id"],
                "type": entry["type"],
                "title": entry["title"],
                "status": entry["status"],
                "version": entry["version"],
                "summary": entry["summary"],
                "tags": json.loads(entry["tags_json"] or "[]"),
            }
        )
        results.append(result)
        if len(results) >= limit:
            break
    return results


def build_knowledge_context(root: Path, task: str, limit: int | None = None) -> str:
    cfg = load_config(root)
    limit = limit or int(cfg.get("knowledge", {}).get("max_context_items", 5))
    rows = search_knowledge(root, task, limit=limit)
    lines = ["# Knowledge Context", "", "## Task", task or "(not provided)", "", "## Current Knowledge"]
    if rows:
        for row in rows:
            lines.append(
                f"- [{row['type']}] {row['title']} v{row['version']} "
                f"`{row['knowledge_id']}`: {row['snippet']} (full: `{row['path']}`)"
            )
    else:
        lines.append("- No current knowledge entries found.")
    lines.extend(
        [
            "",
            "## Rules",
            "- Use only `current` knowledge by default.",
            "- Open the full Markdown file before relying on a principle or research note.",
            "- If a principle changed, update the knowledge entry instead of creating a competing current copy.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_knowledge_context(root: Path, task: str, out: Path, limit: int | None = None) -> str:
    content = build_knowledge_context(root, task, limit)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return str(out)


def current_knowledge_count(root: Path) -> int:
    store = _store(root)
    rows = store.query("SELECT count(*) AS count FROM knowledge_entries WHERE status = 'current'")
    return int(rows[0]["count"] if rows else 0)


def knowledge_conflict_count(root: Path) -> int:
    store = _store(root)
    rows = store.query(
        """
        SELECT count(*) AS count
        FROM (
          SELECT lower(type) AS type_key, lower(title) AS title_key
          FROM knowledge_entries
          WHERE status = 'current'
          GROUP BY type_key, title_key
          HAVING count(*) > 1
        )
        """
    )
    return int(rows[0]["count"] if rows else 0)
