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
from tools.project_memory.services.memory_relations import (
    links_from_markdown, load_links, save_links, validate_links, with_links,
)
from tools.project_memory.time_utils import utc_now
from tools.project_memory.vector.qdrant_store import QdrantLocalStore

CURRENT = "current"
SUPERSEDED = "superseded"
ARCHIVED = "archived"
VALID_STATUSES = {CURRENT, SUPERSEDED, ARCHIVED}


@dataclass(frozen=True)
class RationaleResult:
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


def _rationale_dir(root: Path) -> Path:
    return config_path(root, "rationale_dir")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return slug or stable_id("rationale", value)


def _normalize_type(value: str) -> str:
    return _slugify(value or "decision")


def _normalize_status(value: str) -> str:
    status = (value or CURRENT).strip().lower()
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid rationale status: {value}")
    return status


def _list(values: Iterable[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        for item in str(value).split(","):
            item = item.strip()
            if item and item not in result:
                result.append(item)
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


def _entry_path(root: Path, rationale_type: str, entry_id: str) -> Path:
    return _rationale_dir(root) / rationale_type / f"{entry_id}.md"


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


def _summary_for(content: str, explicit: str | None = None, decision: str | None = None, why: str | None = None) -> str:
    if explicit:
        return explicit.strip()
    if decision:
        return decision.strip()[:320]
    if why:
        return why.strip()[:320]
    for line in _strip_frontmatter(content).splitlines():
        clean = line.strip().lstrip("#").strip()
        if clean:
            return clean[:320]
    return ""


def _frontmatter(
    entry_id: str,
    rationale_type: str,
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
        f"type: {rationale_type}",
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
    rationale_type: str,
    title: str,
    status: str,
    version: int,
    source: str | None,
    tags: list[str],
    supersedes: str | None,
    content: str,
    decision: str | None,
    why: str | None,
    rejected: list[str],
    evidence: list[str],
) -> str:
    body = _strip_frontmatter(content).strip()
    sections: list[str] = []
    if decision:
        sections.extend(["## Decision", "", decision.strip(), ""])
    if why:
        sections.extend(["## Why", "", why.strip(), ""])
    if rejected:
        sections.extend(["## Rejected", ""])
        sections.extend(f"- {item}" for item in rejected)
        sections.append("")
    if evidence:
        sections.extend(["## Evidence", ""])
        sections.extend(f"- {item}" for item in evidence)
        sections.append("")
    if body:
        sections.append(body)
    rendered_body = "\n".join(sections).strip() + "\n"
    return _frontmatter(entry_id, rationale_type, title, status, version, source, tags, supersedes) + rendered_body


def _entry_row(store: SQLiteGraphStore, entry_id: str) -> sqlite3.Row | None:
    rows = store.query("SELECT * FROM rationale_entries WHERE id = ?", (entry_id,))
    return rows[0] if rows else None


def _clear_entry_chunks(store: SQLiteGraphStore, path: str) -> None:
    with store.connect() as conn:
        chunk_ids = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM nodes WHERE kind = 'RationaleChunk' AND path = ?",
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
    rationale_type: str,
    title: str,
    status: str,
    version: int,
    path: str,
    summary: str,
    content: str,
    tags: list[str],
    decision: str | None,
    why: str | None,
    rejected: list[str],
    evidence: list[str],
) -> None:
    _clear_entry_chunks(store, path)
    rationale_id = store.upsert_node(
        kind="Rationale",
        name=title,
        fqn=entry_id,
        path=path,
        language="markdown",
        layer="rationale",
        properties={
            "type": rationale_type,
            "status": status,
            "version": version,
            "summary": summary,
            "decision": decision,
            "why": why,
            "rejected": rejected,
            "evidence": evidence,
            "tags": tags,
        },
    )
    if status != CURRENT:
        return

    vectors = _vectors(root)
    try:
        for index, chunk in enumerate(_chunks(content), start=1):
            chunk_id = store.upsert_node(
                id=stable_id("rationale-chunk", entry_id, index),
                kind="RationaleChunk",
                name=f"{title} chunk {index}",
                fqn=f"rationale:{entry_id}#chunk-{index}",
                path=path,
                language="markdown",
                layer="rationale",
                properties={
                    "content": chunk[:2000],
                    "rationale_id": entry_id,
                    "type": rationale_type,
                    "status": status,
                    "version": version,
                    "summary": summary,
                    "tags": tags,
                },
            )
            store.upsert_edge(rationale_id, chunk_id, "CONTAINS", source="rationale", confidence=1.0)
            with store.connect() as conn:
                conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
                conn.execute(
                    "INSERT INTO chunks_fts(chunk_id, path, fqn, content) VALUES (?, ?, ?, ?)",
                    (chunk_id, path, f"rationale:{entry_id}", f"{title}\n{summary}\n{chunk}"),
                )
            vectors.upsert_chunk(
                chunk_id,
                f"{title}\n{summary}\n{chunk}",
                {
                    "chunk_id": chunk_id,
                    "node_id": chunk_id,
                    "file_path": path,
                    "rationale_id": entry_id,
                    "rationale_type": rationale_type,
                    "title": title,
                    "status": status,
                    "version": version,
                    "kind": "rationale",
                    "hash": sha256_text(content),
                },
            )
    finally:
        vectors.close()


def _save_links(store: SQLiteGraphStore, entry_id: str, links: Iterable[str | dict]) -> None:
    save_links(store, "rationale", entry_id, links)


def add_rationale(
    root: Path,
    rationale_type: str,
    title: str,
    file_path: str | Path,
    entry_id: str | None = None,
    decision: str | None = None,
    why: str | None = None,
    rejected: Iterable[str] | None = None,
    evidence: Iterable[str] | None = None,
    tags: Iterable[str] | None = None,
    source: str | None = None,
    summary: str | None = None,
    supersedes: str | None = None,
    links: Iterable[str | dict] | None = None,
) -> RationaleResult:
    store = _store(root)
    rationale_type = _normalize_type(rationale_type)
    entry_id = _slugify(entry_id or title)
    if _entry_row(store, entry_id):
        raise ValueError(f"rationale entry already exists: {entry_id}")
    if supersedes and not _entry_row(store, _slugify(supersedes)):
        raise ValueError(f"superseded rationale entry not found: {supersedes}")

    content = _read_source(root, file_path)
    link_values = validate_links(store, "rationale", entry_id,
                                 links if links is not None else links_from_markdown(content),
                                 owner_path=_entry_path(root, rationale_type, entry_id))
    tag_list = _list(tags)
    rejected_list = _list(rejected)
    evidence_list = _list(evidence)
    status = CURRENT
    version = 1
    summary_value = _summary_for(content, summary, decision, why)
    path = _entry_path(root, rationale_type, entry_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = _render_markdown(
        entry_id,
        rationale_type,
        title,
        status,
        version,
        source,
        tag_list,
        supersedes,
        content,
        decision,
        why,
        rejected_list,
        evidence_list,
    )
    rendered = with_links(rendered, link_values, "rationale")
    path.write_text(rendered, encoding="utf-8")
    rel = _relative(root, path)
    now = utc_now()
    with store.connect() as conn:
        conn.execute(
            """
            INSERT INTO rationale_entries(
              id, type, title, status, version, decision, why, rejected_json, evidence_json,
              source, tags_json, path, summary, content_hash, supersedes, created_at,
              updated_at, properties_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')
            """,
            (
                entry_id,
                rationale_type,
                title,
                status,
                version,
                decision,
                why,
                json.dumps(rejected_list),
                json.dumps(evidence_list),
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
    _save_links(store, entry_id, link_values)
    if supersedes:
        retire_rationale(root, supersedes, status=SUPERSEDED)
    _index_entry(
        root,
        store,
        entry_id,
        rationale_type,
        title,
        status,
        version,
        rel,
        summary_value,
        rendered,
        tag_list,
        decision,
        why,
        rejected_list,
        evidence_list,
    )
    return RationaleResult(entry_id, rationale_type, title, status, version, rel)


def update_rationale(
    root: Path,
    entry_id: str,
    file_path: str | Path,
    title: str | None = None,
    rationale_type: str | None = None,
    decision: str | None = None,
    why: str | None = None,
    rejected: Iterable[str] | None = None,
    evidence: Iterable[str] | None = None,
    tags: Iterable[str] | None = None,
    source: str | None = None,
    summary: str | None = None,
    links: Iterable[str | dict] | None = None,
) -> RationaleResult:
    store = _store(root)
    entry_id = _slugify(entry_id)
    row = _entry_row(store, entry_id)
    if not row:
        raise ValueError(f"rationale entry not found: {entry_id}")

    content = _read_source(root, file_path)
    # None preserves existing assertions, including stale evidence revisions.
    link_values = (load_links(store, "rationale", entry_id) if links is None
                   else validate_links(store, "rationale", entry_id, links,
                                       owner_path=_entry_path(root, _normalize_type(rationale_type or row["type"]), entry_id)))
    next_type = _normalize_type(rationale_type or row["type"])
    next_title = title or row["title"]
    next_decision = decision if decision is not None else row["decision"]
    next_why = why if why is not None else row["why"]
    next_rejected = _list(rejected if rejected is not None else json.loads(row["rejected_json"] or "[]"))
    next_evidence = _list(evidence if evidence is not None else json.loads(row["evidence_json"] or "[]"))
    next_tags = _list(tags if tags is not None else json.loads(row["tags_json"] or "[]"))
    next_source = source if source is not None else row["source"]
    version = int(row["version"]) + 1
    status = CURRENT
    summary_value = _summary_for(content, summary, next_decision, next_why)
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
        next_decision,
        next_why,
        next_rejected,
        next_evidence,
    )
    rendered = with_links(rendered, link_values, "rationale")
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
            UPDATE rationale_entries
            SET type = ?, title = ?, status = ?, version = ?, decision = ?, why = ?,
                rejected_json = ?, evidence_json = ?, source = ?, tags_json = ?,
                path = ?, summary = ?, content_hash = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                next_type,
                next_title,
                status,
                version,
                next_decision,
                next_why,
                json.dumps(next_rejected),
                json.dumps(next_evidence),
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
        _save_links(store, entry_id, link_values)
    _index_entry(
        root,
        store,
        entry_id,
        next_type,
        next_title,
        status,
        version,
        rel,
        summary_value,
        rendered,
        next_tags,
        next_decision,
        next_why,
        next_rejected,
        next_evidence,
    )
    return RationaleResult(entry_id, next_type, next_title, status, version, rel)


def retire_rationale(root: Path, entry_id: str, status: str = ARCHIVED) -> RationaleResult:
    store = _store(root)
    entry_id = _slugify(entry_id)
    status = _normalize_status(status)
    row = _entry_row(store, entry_id)
    if not row:
        raise ValueError(f"rationale entry not found: {entry_id}")
    now = utc_now()
    with store.connect() as conn:
        conn.execute(
            "UPDATE rationale_entries SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, entry_id),
        )
    _clear_entry_chunks(store, row["path"])
    store.upsert_node(
        kind="Rationale",
        name=row["title"],
        fqn=entry_id,
        path=row["path"],
        language="markdown",
        layer="rationale",
        properties={
            "type": row["type"],
            "status": status,
            "version": int(row["version"]),
            "summary": row["summary"],
            "decision": row["decision"],
            "why": row["why"],
            "rejected": json.loads(row["rejected_json"] or "[]"),
            "evidence": json.loads(row["evidence_json"] or "[]"),
            "tags": json.loads(row["tags_json"] or "[]"),
        },
    )
    return RationaleResult(entry_id, row["type"], row["title"], status, int(row["version"]), row["path"])


def show_rationale(root: Path, entry_id: str) -> str:
    store = _store(root)
    entry_id = _slugify(entry_id)
    row = _entry_row(store, entry_id)
    if not row:
        raise ValueError(f"rationale entry not found: {entry_id}")
    return (root / row["path"]).read_text(encoding="utf-8")


def search_rationale(root: Path, query: str, limit: int = 5, include_archived: bool = False) -> list[dict[str, object]]:
    store = _store(root)
    rows = global_search(root, query, max(limit * 4, limit), layer="rationale")
    entry_paths = {
        str(row["path"]): row
        for row in store.query(
            "SELECT * FROM rationale_entries WHERE status = 'current' OR ?",
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
                "rationale_id": entry["id"],
                "type": entry["type"],
                "title": entry["title"],
                "status": entry["status"],
                "version": entry["version"],
                "summary": entry["summary"],
                "decision": entry["decision"],
                "why": entry["why"],
                "rejected": json.loads(entry["rejected_json"] or "[]"),
                "evidence": json.loads(entry["evidence_json"] or "[]"),
                "tags": json.loads(entry["tags_json"] or "[]"),
            }
        )
        results.append(result)
        if len(results) >= limit:
            break
    return results


def build_rationale_context(root: Path, task: str, limit: int | None = None) -> str:
    cfg = load_config(root)
    limit = limit or int(cfg.get("rationale", {}).get("max_context_items", 5))
    rows = search_rationale(root, task, limit=limit)
    lines = ["# Rationale Context", "", "## Task", task or "(not provided)", "", "## Current Rationale"]
    if rows:
        for row in rows:
            why = f" why: {row['why']}" if row.get("why") else ""
            lines.append(
                f"- [{row['type']}] {row['title']} v{row['version']} "
                f"`{row['rationale_id']}`:{why} {row['snippet']} (full: `{row['path']}`)"
            )
    else:
        lines.append("- No current rationale entries found.")
    lines.extend(
        [
            "",
            "## Rules",
            "- Rationale stores verified decisions, rejected alternatives, and evidence; it must not store hidden chain-of-thought.",
            "- Use only `current` rationale by default.",
            "- Open the full Markdown file before relying on a decision or rejected path.",
            "- If the cause changed, update the rationale entry instead of creating a competing current copy.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_rationale_context(root: Path, task: str, out: Path, limit: int | None = None) -> str:
    content = build_rationale_context(root, task, limit)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return str(out)


def current_rationale_count(root: Path) -> int:
    store = _store(root)
    rows = store.query("SELECT count(*) AS count FROM rationale_entries WHERE status = 'current'")
    return int(rows[0]["count"] if rows else 0)


def rationale_conflict_count(root: Path) -> int:
    store = _store(root)
    rows = store.query(
        """
        SELECT count(*) AS count
        FROM (
          SELECT lower(type) AS type_key, lower(title) AS title_key
          FROM rationale_entries
          WHERE status = 'current'
          GROUP BY type_key, title_key
          HAVING count(*) > 1
        )
        """
    )
    return int(rows[0]["count"] if rows else 0)
