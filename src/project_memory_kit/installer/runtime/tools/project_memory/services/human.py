from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.project_memory.config import config_path
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.hashing import sha256_text, stable_id
from tools.project_memory.services.human_graph_html import render_human_graph_html
from tools.project_memory.services.knowledge import update_knowledge
from tools.project_memory.services.modules import module_enabled
from tools.project_memory.services.rationale import update_rationale
from tools.project_memory.services.search import format_search_result, search as search_service


GENERATED_DIRS = ("knowledge", "rationale")


@dataclass(frozen=True)
class HumanExportReport:
    enabled: bool
    path: str
    generated: int
    removed: int
    indexed: int


@dataclass(frozen=True)
class HumanGraphReport:
    enabled: bool
    json_path: str
    mermaid_path: str
    nodes: int
    edges: int


@dataclass(frozen=True)
class HumanGraphHtmlReport:
    enabled: bool
    html_path: str
    json_path: str
    nodes: int
    edges: int


@dataclass(frozen=True)
class HumanSyncReport:
    enabled: bool
    path: str
    synced: int
    skipped: int
    conflicts: list[str]
    generated: int
    indexed: int


def _store(root: Path) -> SQLiteGraphStore:
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    return store


def _human_dir(root: Path) -> Path:
    return config_path(root, "human_dir")


def _require_enabled(root: Path) -> None:
    if not module_enabled(root, "human"):
        raise ValueError("human module is disabled. Run `./pmem modules set human --enabled true` first.")


def _json_list(value: Any) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _quoted(value: Any) -> str:
    return json.dumps(str(value or ""), ensure_ascii=False)


def _strip_frontmatter(content: str) -> str:
    if not content.startswith("---\n"):
        return content
    marker = content.find("\n---", 4)
    if marker == -1:
        return content
    end = content.find("\n", marker + 4)
    return "" if end == -1 else content[end + 1 :]


def _frontmatter_value(content: str, name: str) -> str:
    if not content.startswith("---\n"):
        return ""
    marker = content.find("\n---", 4)
    if marker == -1:
        return ""
    for line in content[4:marker].splitlines():
        key, _, value = line.partition(":")
        if key.strip() != name:
            continue
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            try:
                return str(json.loads(value))
            except json.JSONDecodeError:
                return value.strip('"')
        return value
    return ""


def _note_body(content: str) -> str:
    body = _strip_frontmatter(content)
    marker = re.search(r"(?m)^##\s+Note\s*$", body)
    if not marker:
        return body.strip()
    return body[marker.end() :].strip()


def _body_hash(content: str) -> str:
    return sha256_text(content.strip())


def _read_source(root: Path, rel_path: str) -> str:
    path = Path(rel_path)
    if not path.is_absolute():
        path = root / path
    return path.read_text(encoding="utf-8", errors="replace")


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
        current = block
    if current:
        chunks.append(current)
    return chunks or [content[:max_chars]]


def _clear_human_index(store: SQLiteGraphStore) -> None:
    with store.connect() as conn:
        ids = [row["id"] for row in conn.execute("SELECT id FROM nodes WHERE layer = 'human'").fetchall()]
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        conn.execute(f"DELETE FROM chunks_fts WHERE chunk_id IN ({placeholders})", tuple(ids))
        conn.execute("DELETE FROM nodes WHERE layer = 'human'")


def _clear_generated_files(root: Path) -> int:
    removed = 0
    base = _human_dir(root)
    for dirname in GENERATED_DIRS:
        folder = base / dirname
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*.md")):
            path.unlink()
            removed += 1
    for path in [base / "index.md"]:
        if path.exists():
            path.unlink()
            removed += 1
    return removed


def _frontmatter(layer: str, row: dict[str, Any], rel_path: str, body: str) -> str:
    tags = _json_list(row.get("tags_json"))
    lines = [
        "---",
        f"pmem_human_id: {_quoted(layer + ':' + str(row['id']))}",
        f"source_layer: {_quoted(layer)}",
        f"source_id: {_quoted(row['id'])}",
        f"source_path: {_quoted(row['path'])}",
        f"source_content_hash: {_quoted(row.get('content_hash'))}",
        f"note_body_hash: {_quoted(_body_hash(_strip_frontmatter(body)))}",
        f"title: {_quoted(row['title'])}",
        f"status: {_quoted(row['status'])}",
        f"version: {int(row['version'])}",
        f"human_path: {_quoted(rel_path)}",
    ]
    if tags:
        lines.append("tags:")
        lines.extend(f"  - {_quoted(tag)}" for tag in tags)
    lines.extend(["---", ""])
    return "\n".join(lines)


def _render_doc(layer: str, row: dict[str, Any], body: str, rel_path: str) -> str:
    title = str(row["title"])
    source_id = str(row["id"])
    source_path = str(row["path"])
    return (
        _frontmatter(layer, row, rel_path, body)
        + f"# {title}\n\n"
        + "## PMEM Source\n\n"
        + f"- Source: `{layer}:{source_id}`\n"
        + f"- Source file: `{source_path}`\n"
        + f"- Version: `{int(row['version'])}`\n"
        + f"- Backlink: [[{layer}:{source_id}]]\n\n"
        + "## Note\n\n"
        + _strip_frontmatter(body).strip()
        + "\n"
    )


def _current_rows(store: SQLiteGraphStore, table: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in store.query(
            f"SELECT * FROM {table} WHERE status = 'current' ORDER BY updated_at DESC, id ASC"
        )
    ]


def _current_row(store: SQLiteGraphStore, layer: str, entry_id: str) -> dict[str, Any] | None:
    table = "knowledge_entries" if layer == "knowledge" else "rationale_entries"
    rows = store.query(f"SELECT * FROM {table} WHERE id = ? AND status = 'current'", (entry_id,))
    return dict(rows[0]) if rows else None


def _sync_source_path(root: Path, layer: str, entry_id: str) -> Path:
    path = root / ".project-memory" / "tmp" / "human-sync" / layer / f"{entry_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _human_note_paths(root: Path) -> list[Path]:
    base = _human_dir(root)
    paths: list[Path] = []
    for layer in GENERATED_DIRS:
        folder = base / layer
        if folder.exists():
            paths.extend(sorted(folder.rglob("*.md")))
    return paths


def _write_docs(root: Path, store: SQLiteGraphStore) -> list[tuple[str, str, str, str]]:
    written: list[tuple[str, str, str, str]] = []
    base = _human_dir(root)
    base.mkdir(parents=True, exist_ok=True)
    for layer, table in [("knowledge", "knowledge_entries"), ("rationale", "rationale_entries")]:
        folder = base / layer
        folder.mkdir(parents=True, exist_ok=True)
        for row in _current_rows(store, table):
            try:
                source = _read_source(root, str(row["path"]))
            except FileNotFoundError:
                continue
            rel_path = f".project-memory/human/{layer}/{row['id']}.md"
            content = _render_doc(layer, row, source, rel_path)
            path = root / rel_path
            path.write_text(content, encoding="utf-8")
            written.append((layer, str(row["id"]), str(row["title"]), rel_path))
    _write_index(root, written)
    return written


def _write_index(root: Path, entries: list[tuple[str, str, str, str]]) -> None:
    lines = ["# Human Memory", "", "Generated from current PMEM knowledge and rationale records.", ""]
    for layer in GENERATED_DIRS:
        lines.extend([f"## {layer.title()}", ""])
        layer_entries = [entry for entry in entries if entry[0] == layer]
        if not layer_entries:
            lines.extend(["No current records.", ""])
            continue
        for _, entry_id, title, rel_path in layer_entries:
            link_path = rel_path.replace(".project-memory/human/", "").removesuffix(".md")
            lines.append(f"- [[{link_path}|{title}]] (`{layer}:{entry_id}`)")
        lines.append("")
    (_human_dir(root) / "index.md").write_text("\n".join(lines), encoding="utf-8")


def _index_docs(root: Path, store: SQLiteGraphStore, entries: list[tuple[str, str, str, str]]) -> int:
    indexed = 0
    for source_layer, source_id, title, rel_path in entries:
        path = root / rel_path
        content = path.read_text(encoding="utf-8")
        note_id = store.upsert_node(
            id=stable_id("human-note", source_layer, source_id),
            kind="HumanNote",
            name=title,
            fqn=f"human:{source_layer}:{source_id}",
            path=rel_path,
            language="markdown",
            layer="human",
            hash=sha256_text(content),
            properties={"source_layer": source_layer, "source_id": source_id},
        )
        for index, chunk in enumerate(_chunks(content), start=1):
            chunk_id = store.upsert_node(
                id=stable_id("human-chunk", source_layer, source_id, index),
                kind="HumanChunk",
                name=f"{title} chunk {index}",
                fqn=f"human:{source_layer}:{source_id}#chunk-{index}",
                path=rel_path,
                language="markdown",
                layer="human",
                properties={"content": chunk[:2000], "source_layer": source_layer, "source_id": source_id},
            )
            store.upsert_edge(note_id, chunk_id, "HAS_CHUNK", source="human", confidence=1.0)
            with store.connect() as conn:
                conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
                conn.execute(
                    "INSERT INTO chunks_fts(chunk_id, path, fqn, content) VALUES (?, ?, ?, ?)",
                    (chunk_id, rel_path, f"human:{source_layer}:{source_id}", chunk),
                )
            indexed += 1
    return indexed


def _graph_node_id(layer: str, entry_id: str) -> str:
    return f"{layer}:{entry_id}"


def _mermaid_id(value: str) -> str:
    return "n_" + re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")


def _graph_rows(store: SQLiteGraphStore) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    current: set[str] = set()
    for layer, table in [("knowledge", "knowledge_entries"), ("rationale", "rationale_entries")]:
        for row in _current_rows(store, table):
            node_id = _graph_node_id(layer, str(row["id"]))
            current.add(node_id)
            nodes.append(
                {
                    "id": node_id,
                    "layer": layer,
                    "title": row["title"],
                    "type": row["type"],
                    "status": row["status"],
                    "path": row["path"],
                }
            )

    edges: list[dict[str, Any]] = []
    for layer, table, link_table, fk in [
        ("knowledge", "knowledge_entries", "knowledge_links", "knowledge_id"),
        ("rationale", "rationale_entries", "rationale_links", "rationale_id"),
    ]:
        for row in store.query(f"SELECT {fk}, relation, target FROM {link_table} ORDER BY {fk}, target"):
            source_id = _graph_node_id(layer, str(row[fk]))
            if source_id not in current:
                continue
            target = str(row["target"])
            target_id = target if ":" in target else _graph_node_id("external", target)
            if target_id not in current and not any(node["id"] == target_id for node in nodes):
                nodes.append({"id": target_id, "layer": "external", "title": target, "type": "external", "path": ""})
            edges.append({"source": source_id, "target": target_id, "relation": row["relation"]})
    return nodes, edges


def _write_mermaid(path: Path, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    lines = ["graph LR"]
    for node in nodes:
        label = f"{node['layer']}: {node['title']}".replace('"', "'")
        lines.append(f"  {_mermaid_id(str(node['id']))}[\"{label}\"]")
    for edge in edges:
        relation = str(edge["relation"]).replace('"', "'")
        lines.append(f"  {_mermaid_id(str(edge['source']))} -- \"{relation}\" --> {_mermaid_id(str(edge['target']))}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def human_graph(root: Path) -> HumanGraphReport:
    _require_enabled(root)
    store = _store(root)
    base = _human_dir(root)
    base.mkdir(parents=True, exist_ok=True)
    nodes, edges = _graph_rows(store)
    json_path = base / "graph.json"
    mermaid_path = base / "graph.mmd"
    json_path.write_text(json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_mermaid(mermaid_path, nodes, edges)
    return HumanGraphReport(True, str(json_path), str(mermaid_path), len(nodes), len(edges))


def format_human_graph(report: HumanGraphReport) -> str:
    return (
        "Human graph\n"
        f"- json: {report.json_path}\n"
        f"- mermaid: {report.mermaid_path}\n"
        f"- nodes: {report.nodes}\n"
        f"- edges: {report.edges}\n"
    )


def human_graph_html(root: Path) -> HumanGraphHtmlReport:
    report = human_graph(root)
    data = json.loads(Path(report.json_path).read_text(encoding="utf-8"))
    html_path = _human_dir(root) / "graph.html"
    html_path.write_text(render_human_graph_html(data), encoding="utf-8")
    return HumanGraphHtmlReport(True, str(html_path), report.json_path, report.nodes, report.edges)


def format_human_graph_html(report: HumanGraphHtmlReport) -> str:
    return (
        "Human graph HTML\n"
        f"- html: {report.html_path}\n"
        f"- json: {report.json_path}\n"
        f"- nodes: {report.nodes}\n"
        f"- edges: {report.edges}\n"
    )


def human_status(root: Path) -> dict[str, Any]:
    enabled = module_enabled(root, "human")
    base = _human_dir(root)
    notes = len(list(base.rglob("*.md"))) if base.exists() else 0
    return {"enabled": enabled, "path": str(base), "notes": notes}


def format_human_status(status: dict[str, Any]) -> str:
    state = "enabled" if status["enabled"] else "disabled"
    return f"Human layer: {state}\npath={status['path']}\nnotes={status['notes']}\n"


def export_human(root: Path) -> HumanExportReport:
    _require_enabled(root)
    store = _store(root)
    removed = _clear_generated_files(root)
    _clear_human_index(store)
    entries = _write_docs(root, store)
    indexed = _index_docs(root, store, entries)
    return HumanExportReport(True, str(_human_dir(root)), len(entries) + 1, removed, indexed)


def format_human_export(report: HumanExportReport) -> str:
    return (
        "Human export\n"
        f"- path: {report.path}\n"
        f"- generated: {report.generated}\n"
        f"- removed: {report.removed}\n"
        f"- indexed_chunks: {report.indexed}\n"
    )


def sync_human(root: Path) -> HumanSyncReport:
    _require_enabled(root)
    store = _store(root)
    conflicts: list[str] = []
    pending: list[tuple[str, str, Path, str]] = []
    skipped = 0

    for path in _human_note_paths(root):
        content = path.read_text(encoding="utf-8", errors="replace")
        layer = _frontmatter_value(content, "source_layer")
        entry_id = _frontmatter_value(content, "source_id")
        exported_hash = _frontmatter_value(content, "source_content_hash")
        exported_body_hash = _frontmatter_value(content, "note_body_hash")
        if layer not in GENERATED_DIRS or not entry_id:
            skipped += 1
            continue
        current = _current_row(store, layer, entry_id)
        if not current:
            conflicts.append(f"{path.relative_to(root)}: source record not found")
            continue
        body = _note_body(content)
        if not exported_body_hash:
            try:
                exported_body_hash = _body_hash(_strip_frontmatter(_read_source(root, str(current["path"]))))
            except FileNotFoundError:
                exported_body_hash = ""
        human_changed = bool(exported_body_hash) and _body_hash(body) != exported_body_hash
        source_changed = bool(exported_hash) and str(current.get("content_hash") or "") != exported_hash
        if human_changed and source_changed:
            conflicts.append(f"{path.relative_to(root)}: human note and source record both changed")
            continue
        if not human_changed:
            skipped += 1
            continue
        source_path = _sync_source_path(root, layer, entry_id)
        source_path.write_text(body.strip() + "\n", encoding="utf-8")
        pending.append((layer, entry_id, source_path, str(path.relative_to(root))))

    if conflicts:
        return HumanSyncReport(True, str(_human_dir(root)), 0, skipped, conflicts, 0, 0)

    for layer, entry_id, source_path, _ in pending:
        if layer == "knowledge":
            update_knowledge(root, entry_id, source_path)
        else:
            update_rationale(root, entry_id, source_path)

    export_report = export_human(root)
    return HumanSyncReport(
        True,
        str(_human_dir(root)),
        len(pending),
        skipped,
        [],
        export_report.generated,
        export_report.indexed,
    )


def format_human_sync(report: HumanSyncReport) -> str:
    lines = [
        "Human sync",
        f"- path: {report.path}",
        f"- synced: {report.synced}",
        f"- skipped: {report.skipped}",
        f"- generated: {report.generated}",
        f"- indexed_chunks: {report.indexed}",
    ]
    if report.conflicts:
        lines.append("- conflicts:")
        lines.extend(f"  - {item}" for item in report.conflicts)
    return "\n".join(lines) + "\n"


def search_human(root: Path, query: str, limit: int = 10) -> list[dict[str, Any]]:
    _require_enabled(root)
    return [dict(item) for item in search_service(root, query, limit=limit, layer="human")]


def format_human_search(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No human results.\n"
    return "\n".join(format_search_result(row) for row in rows) + "\n"
