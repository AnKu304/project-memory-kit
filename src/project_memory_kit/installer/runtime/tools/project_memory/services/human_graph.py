from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tools.project_memory.graph.sqlite_store import SQLiteGraphStore


GENERATED_LAYERS = ("knowledge", "rationale")


def _json_list(value: Any) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _graph_node_id(layer: str, entry_id: str) -> str:
    return f"{layer}:{entry_id}"


def _clean_graph_target(value: Any) -> str:
    clean = str(value or "").strip().strip("`'\"[](){}<>")
    while clean.endswith((",", ".", ";")):
        clean = clean[:-1].rstrip()
    return clean


def _external_node_id(target: str) -> str:
    return _graph_node_id("external", target)


def _current_rows(store: SQLiteGraphStore, table: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in store.query(
            f"SELECT * FROM {table} WHERE status = 'current' ORDER BY updated_at DESC, id ASC"
        )
    ]


def _graph_aliases(nodes: list[dict[str, Any]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in nodes:
        node_id = str(node["id"])
        raw_values = [
            node_id,
            node_id.split(":", 1)[-1],
            str(node.get("path") or ""),
            Path(str(node.get("path") or "")).name,
            str(node.get("title") or ""),
        ]
        for value in raw_values:
            clean = _clean_graph_target(value)
            if clean:
                aliases.setdefault(clean.lower(), node_id)
    return aliases


def _resolve_graph_target(
    target: str,
    nodes: list[dict[str, Any]],
    current: set[str],
    aliases: dict[str, str],
) -> str:
    clean = _clean_graph_target(target)
    if not clean:
        return ""
    target_id = aliases.get(clean.lower())
    if not target_id and ":" in clean and clean.split(":", 1)[0] in GENERATED_LAYERS:
        target_id = clean
    if target_id and target_id in current:
        return target_id

    external_id = _external_node_id(clean)
    if not any(node["id"] == external_id for node in nodes):
        nodes.append({"id": external_id, "layer": "external", "title": clean, "type": "external", "path": ""})
    return external_id


def _add_graph_edge(
    edges: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    source: str,
    target: str,
    relation: str,
) -> None:
    if not source or not target or source == target:
        return
    key = (source, target, relation)
    if key in seen:
        return
    seen.add(key)
    edges.append({"source": source, "target": target, "relation": relation})


def _extract_graph_mentions(content: str) -> list[str]:
    mentions: list[str] = []
    patterns = [
        r"\b(?:knowledge|rationale):[A-Za-z0-9_-]+\b",
        r"https?://[^\s)`>\"]+",
        r"\barXiv:\d{4}\.\d{4,5}\b",
        r"(?<![\w./:-])(?:\.{1,2}/|/|\.project-memory/|\.agents/|src/|tests/|tools/|docs/)[A-Za-z0-9_./-]+",
        r"(?<![\w.-])(?:README|AGENTS|PROJECT_RULES|TASK)\.md\b",
        r"(?<![\w.-])pyproject\.toml\b",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, content):
            clean = _clean_graph_target(match)
            if clean and clean not in mentions:
                mentions.append(clean)
    return mentions[:40]


def _row_body(root: Path, row: dict[str, Any]) -> str:
    path = Path(str(row["path"]))
    if not path.is_absolute():
        path = root / path
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def _build_current_nodes(store: SQLiteGraphStore) -> tuple[list[dict[str, Any]], set[str], list[tuple[str, dict[str, Any]]]]:
    nodes: list[dict[str, Any]] = []
    current: set[str] = set()
    entries: list[tuple[str, dict[str, Any]]] = []
    for layer, table in [("knowledge", "knowledge_entries"), ("rationale", "rationale_entries")]:
        for row in _current_rows(store, table):
            node_id = _graph_node_id(layer, str(row["id"]))
            current.add(node_id)
            entries.append((layer, row))
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
    return nodes, current, entries


def _add_link_table_edges(
    store: SQLiteGraphStore,
    nodes: list[dict[str, Any]],
    current: set[str],
    aliases: dict[str, str],
    edges: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
) -> None:
    for layer, link_table, fk in [
        ("knowledge", "knowledge_links", "knowledge_id"),
        ("rationale", "rationale_links", "rationale_id"),
    ]:
        for row in store.query(f"SELECT {fk}, relation, target FROM {link_table} ORDER BY {fk}, target"):
            source_id = _graph_node_id(layer, str(row[fk]))
            if source_id not in current:
                continue
            target_id = _resolve_graph_target(str(row["target"]), nodes, current, aliases)
            _add_graph_edge(edges, seen, source_id, target_id, str(row["relation"]))


def _add_structured_and_mention_edges(
    store: SQLiteGraphStore,
    nodes: list[dict[str, Any]],
    current: set[str],
    aliases: dict[str, str],
    entries: list[tuple[str, dict[str, Any]]],
    edges: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
) -> None:
    for layer, row in entries:
        source_id = _graph_node_id(layer, str(row["id"]))
        if source_id not in current:
            continue

        structured_targets: list[tuple[str, str]] = []
        if row.get("source"):
            structured_targets.append(("source", str(row["source"])))
        if row.get("supersedes"):
            structured_targets.append(("supersedes", str(row["supersedes"])))
        for evidence in _json_list(row.get("evidence_json")):
            structured_targets.append(("evidence", evidence))

        for relation, target in structured_targets:
            target_id = _resolve_graph_target(target, nodes, current, aliases)
            _add_graph_edge(edges, seen, source_id, target_id, relation)

        for mention in _extract_graph_mentions(_row_body(store.root, row)):
            target_id = _resolve_graph_target(mention, nodes, current, aliases)
            _add_graph_edge(edges, seen, source_id, target_id, "mentions")


def build_human_graph_rows(store: SQLiteGraphStore) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes, current, entries = _build_current_nodes(store)
    aliases = _graph_aliases(nodes)
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    _add_link_table_edges(store, nodes, current, aliases, edges, seen)
    _add_structured_and_mention_edges(store, nodes, current, aliases, entries, edges, seen)
    return nodes, edges


def _mermaid_id(value: str) -> str:
    return "n_" + re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")


def write_human_graph_mermaid(path: Path, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    lines = ["graph LR"]
    for node in nodes:
        label = f"{node['layer']}: {node['title']}".replace('"', "'")
        lines.append(f"  {_mermaid_id(str(node['id']))}[\"{label}\"]")
    for edge in edges:
        relation = str(edge["relation"]).replace('"', "'")
        lines.append(f"  {_mermaid_id(str(edge['source']))} -- \"{relation}\" --> {_mermaid_id(str(edge['target']))}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
