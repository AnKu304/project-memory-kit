from __future__ import annotations

import json
from pathlib import Path

from tools.project_memory.config import config_path, load_config
from tools.project_memory.git_diff import changed_files, untracked_files
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.hashing import sha256_file
from tools.project_memory.ignore import should_index
from tools.project_memory.parsers.js_ts import JsTsParser
from tools.project_memory.parsers.js_ts_imports import JS_TS_EXTENSIONS, language_for_path as js_ts_language_for_path
from tools.project_memory.parsers.python_ast import PythonAstParser
from tools.project_memory.parsers.symbol_model import ParseResult, Symbol
from tools.project_memory.vector.qdrant_store import QdrantLocalStore


PYTHON_PARSER = PythonAstParser()
JS_TS_PARSER = JsTsParser()
NEXT_ROUTE_FILES = {"page", "layout", "route", "loading", "error", "not-found", "template", "default"}


def _iter_files(root: Path, mode: str, store: SQLiteGraphStore | None = None) -> list[Path]:
    all_files = [path for path in root.rglob("*") if should_index(root, path)]
    if mode == "changed":
        changed = list(dict.fromkeys([*changed_files(root), *untracked_files(root)]))
        if changed:
            changed_set = set(changed)
            candidates = [path for path in all_files if path.relative_to(root).as_posix() in changed_set]
            if store is not None:
                known = {path.relative_to(root).as_posix() for path in candidates}
                candidates.extend(
                    path
                    for path in all_files
                    if path.relative_to(root).as_posix() not in known
                    and store.file_hash(path.relative_to(root).as_posix()) is None
                )
            return candidates
    return all_files


def _cleanup_removed_files(root: Path, store: SQLiteGraphStore) -> int:
    current_paths = {path.relative_to(root).as_posix() for path in root.rglob("*") if should_index(root, path)}
    removed_paths = store.indexed_file_paths() - current_paths
    for rel in sorted(removed_paths):
        store.clear_removed_file_memory(rel)
    return len(removed_paths)


def _lines_for(path: Path, start_line: int, end_line: int) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[max(start_line - 1, 0) : end_line])


def _parser_for(path: Path):
    if path.suffix == ".py":
        return PYTHON_PARSER, "python", "python_ast"
    if path.suffix in JS_TS_EXTENSIONS:
        return JS_TS_PARSER, js_ts_language_for_path(path), "js_ts"
    return None, _language_for_path(path), "text"


def _language_for_path(path: Path) -> str | None:
    if path.suffix == ".py":
        return "python"
    if path.suffix in JS_TS_EXTENSIONS:
        return js_ts_language_for_path(path)
    return None


def _next_route_info(path: Path, rel: str) -> dict[str, str] | None:
    if path.suffix not in JS_TS_EXTENSIONS or path.stem not in NEXT_ROUTE_FILES:
        return None
    parts = Path(rel).parts
    try:
        app_index = parts.index("app")
    except ValueError:
        return None
    route_parts = []
    for part in parts[app_index + 1 : -1]:
        if part.startswith("(") and part.endswith(")"):
            continue
        route_parts.append(part)
    route = "/" + "/".join(route_parts)
    if route != "/":
        route = route.rstrip("/")
    route_kind = "api_route" if path.stem == "route" else "page_route"
    return {
        "framework": "next",
        "route": route,
        "route_kind": route_kind,
        "route_file": path.name,
    }


def _target_for_name(name: str, symbols: list[Symbol], symbol_ids: dict[str, str]) -> str | None:
    if not name:
        return None
    candidates = [name]
    if "." in name:
        candidates.append(name.rsplit(".", 1)[-1])
    for candidate in candidates:
        for symbol in symbols:
            if symbol.name == candidate or symbol.fqn.endswith("." + candidate) or symbol.fqn.endswith("." + name):
                return symbol_ids.get(symbol.fqn)
    return None


def _index_parse_result(
    path: Path,
    rel: str,
    file_id: str,
    file_hash: str,
    language: str,
    parser_name: str,
    result: ParseResult,
    store: SQLiteGraphStore,
    vectors: QdrantLocalStore,
) -> list[str]:
    module_id = store.upsert_node(kind="Module", name=result.module, fqn=result.module, path=rel, language=language)
    store.upsert_edge(file_id, module_id, "DEFINES", evidence=rel)

    symbol_ids: dict[str, str] = {}
    for symbol in result.symbols:
        symbol_id = store.upsert_node(
            kind="Symbol",
            name=symbol.name,
            fqn=symbol.fqn,
            path=rel,
            language=language,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            properties={
                "kind": symbol.kind,
                "signature": symbol.signature,
                "docstring": symbol.docstring,
                "decorators": symbol.decorators,
                "bases": symbol.bases,
                "calls": symbol.calls,
                "references": symbol.references,
            },
        )
        symbol_ids[symbol.fqn] = symbol_id
        store.upsert_edge(file_id, symbol_id, "DEFINES", evidence=symbol.fqn)
        chunk = _lines_for(path, symbol.start_line, symbol.end_line)
        chunk_id = store.upsert_chunk(rel, symbol.fqn, symbol.start_line, symbol.end_line, chunk)
        store.upsert_edge(chunk_id, symbol_id, "DESCRIBES", evidence=symbol.fqn)
        vectors.upsert_chunk(
            chunk_id,
            chunk,
            {
                "chunk_id": chunk_id,
                "node_id": chunk_id,
                "file_path": rel,
                "symbol_id": symbol_id,
                "symbol_fqn": symbol.fqn,
                "start_line": symbol.start_line,
                "end_line": symbol.end_line,
                "kind": "symbol",
                "hash": file_hash,
            },
        )

    for symbol in result.symbols:
        symbol_id = symbol_ids.get(symbol.fqn)
        if not symbol_id:
            continue
        for call in symbol.calls:
            target = _target_for_name(call, result.symbols, symbol_ids)
            if target and target != symbol_id:
                store.upsert_edge(symbol_id, target, "CALLS", confidence=0.55, evidence=call)
        for reference in symbol.references:
            target = _target_for_name(reference, result.symbols, symbol_ids)
            if target and target != symbol_id:
                store.upsert_edge(symbol_id, target, "REFERENCES", confidence=0.35, evidence=reference)
        for base in symbol.bases:
            target = _target_for_name(base, result.symbols, symbol_ids)
            if target:
                store.upsert_edge(symbol_id, target, "INHERITS", confidence=0.65, evidence=base)

    for item in result.imports:
        if item.target_path:
            target_path = Path(item.target_path)
            edge_source = f"import:{item.kind}:{item.name or '*'}:{item.alias or ''}"
            target_id = store.upsert_node(
                kind="File",
                name=target_path.name,
                fqn=item.target_path,
                path=item.target_path,
                language=_language_for_path(target_path),
            )
            store.upsert_edge(
                file_id,
                target_id,
                "IMPORTS",
                source=edge_source,
                confidence=0.85,
                evidence=item.module,
                properties={"name": item.name, "alias": item.alias, "import_kind": item.kind, "line": item.line},
            )
    store.update_file_state(rel, file_hash, parser_name, result.warnings)
    return [f"{rel}: {warning}" for warning in result.warnings]


def _json_props(value: str | None) -> dict:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _symbols_for_path(store: SQLiteGraphStore, path: str) -> list[dict]:
    rows = store.query(
        """
        SELECT id, name, fqn, path, properties_json
        FROM nodes
        WHERE kind = 'Symbol' AND path = ?
        """,
        (path,),
    )
    return [dict(row) for row in rows]


def _matching_symbols(store: SQLiteGraphStore, path: str, name: str | None, fallback_name: str | None = None) -> list[dict]:
    if not name:
        return []
    names = [name]
    if name == "default" and fallback_name:
        names.append(fallback_name)
    symbols = _symbols_for_path(store, path)
    matches: list[dict] = []
    for candidate in names:
        for symbol in symbols:
            if symbol["name"] == candidate or str(symbol["fqn"]).endswith("." + candidate):
                matches.append(symbol)
        if matches:
            return matches
    return matches


def _outgoing_imports(store: SQLiteGraphStore, path: str) -> list[dict]:
    rows = store.query(
        """
        SELECT dst.path AS dst_path, e.evidence, e.properties_json
        FROM edges e
        JOIN nodes src ON src.id = e.src_id
        JOIN nodes dst ON dst.id = e.dst_id
        WHERE e.kind = 'IMPORTS' AND src.kind = 'File' AND src.path = ?
        """,
        (path,),
    )
    return [dict(row) for row in rows]


def _resolve_imported_symbols(
    store: SQLiteGraphStore,
    target_path: str,
    name: str | None,
    fallback_name: str | None,
    seen: set[tuple[str, str | None]],
) -> list[dict]:
    key = (target_path, name)
    if key in seen:
        return []
    seen.add(key)
    direct = _matching_symbols(store, target_path, name, fallback_name)
    if direct:
        return direct

    resolved: list[dict] = []
    for edge in _outgoing_imports(store, target_path):
        props = _json_props(edge.get("properties_json"))
        if props.get("import_kind") != "export":
            continue
        exported_name = props.get("alias") or props.get("name")
        if props.get("name") != "*" and exported_name != name:
            continue
        next_name = name if props.get("name") == "*" else props.get("name")
        resolved.extend(_resolve_imported_symbols(store, str(edge["dst_path"]), next_name, fallback_name, seen))
    return resolved


def _token_used(token: str, props: dict, key: str) -> bool:
    values = props.get(key, [])
    if not isinstance(values, list):
        return False
    return any(value == token or str(value).startswith(token + ".") for value in values)


def _bind_cross_file_symbols(store: SQLiteGraphStore) -> int:
    imports = store.query(
        """
        SELECT src.path AS src_path, dst.path AS dst_path, e.evidence, e.properties_json
        FROM edges e
        JOIN nodes src ON src.id = e.src_id
        JOIN nodes dst ON dst.id = e.dst_id
        WHERE e.kind = 'IMPORTS' AND src.kind = 'File' AND dst.kind = 'File'
        """
    )
    bound = 0
    for item in imports:
        props = _json_props(item["properties_json"])
        if props.get("import_kind") not in {"import", "dynamic_import", "require"}:
            continue
        name = props.get("name")
        alias = props.get("alias")
        if name in {None, "*"}:
            continue
        token = alias or name
        targets = _resolve_imported_symbols(store, item["dst_path"], name, token, set())
        if not targets:
            continue
        for source_symbol in _symbols_for_path(store, item["src_path"]):
            source_props = _json_props(source_symbol.get("properties_json"))
            calls = _token_used(token, source_props, "calls")
            refs = calls or _token_used(token, source_props, "references")
            if not refs:
                continue
            for target in targets:
                if source_symbol["id"] == target["id"]:
                    continue
                evidence = f"{item['evidence']}:{name}" + (f" as {alias}" if alias else "")
                store.upsert_edge(
                    source_symbol["id"],
                    target["id"],
                    "REFERENCES",
                    source="binding",
                    confidence=0.82,
                    evidence=evidence,
                    properties={"binding": "imported_symbol", "token": token},
                )
                bound += 1
                if calls:
                    store.upsert_edge(
                        source_symbol["id"],
                        target["id"],
                        "CALLS",
                        source="binding",
                        confidence=0.78,
                        evidence=evidence,
                        properties={"binding": "imported_symbol", "token": token},
                    )
                    bound += 1
    return bound


def index_project(root: Path, mode: str = "changed") -> str:
    cfg = load_config(root)
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    vector_cfg = cfg.get("vector", {})
    vectors = QdrantLocalStore(
        config_path(root, "qdrant_path"),
        cfg.get("memory", {}).get("vector_size", 64),
        backend=vector_cfg.get("backend", "auto"),
        collection=vector_cfg.get("collection", "project_memory_chunks"),
        model_name=vector_cfg.get("embedding_model"),
    )

    files = [path for path in _iter_files(root, mode, store) if should_index(root, path)]
    indexed = 0
    skipped = 0
    warnings: list[str] = []
    removed = _cleanup_removed_files(root, store)

    project_id = store.upsert_node(kind="Project", name=root.name, fqn=root.name, path=".")

    for path in files:
        rel = path.relative_to(root).as_posix()
        file_hash = sha256_file(path)
        if mode == "changed" and store.file_hash(rel) == file_hash:
            skipped += 1
            continue

        store.clear_generated_file_memory(rel)
        parser, language, parser_name = _parser_for(path)
        file_id = store.upsert_node(
            kind="File",
            name=path.name,
            fqn=rel,
            path=rel,
            language=language,
            hash=file_hash,
        )
        store.upsert_edge(project_id, file_id, "CONTAINS", evidence=rel)
        route_info = _next_route_info(path, rel)
        if route_info:
            route_id = store.upsert_node(
                kind="Route",
                name=route_info["route"],
                fqn=f"next:{route_info['route_kind']}:{route_info['route']}",
                path=rel,
                language=language,
                layer="frontend",
                properties=route_info,
            )
            store.upsert_edge(file_id, route_id, "DEFINES", confidence=0.9, evidence=route_info["route"])

        if parser is not None:
            result = parser.parse(root, path)
            warnings.extend(
                _index_parse_result(path, rel, file_id, file_hash, language or "text", parser_name, result, store, vectors)
            )
        else:
            content = path.read_text(encoding="utf-8", errors="replace")
            line_count = max(1, len(content.splitlines()))
            chunk_id = store.upsert_chunk(rel, rel, 1, line_count, content)
            store.upsert_edge(chunk_id, file_id, "DESCRIBES", evidence=rel)
            vectors.upsert_chunk(
                chunk_id,
                content,
                {
                    "chunk_id": chunk_id,
                    "node_id": chunk_id,
                    "file_path": rel,
                    "symbol_id": None,
                    "symbol_fqn": None,
                    "start_line": 1,
                    "end_line": line_count,
                    "kind": "file",
                    "hash": file_hash,
                },
            )
            store.update_file_state(rel, file_hash, "text", [])
        indexed += 1

    summary = [f"indexed={indexed}", f"skipped={skipped}", f"removed={removed}", f"mode={mode}"]
    bound = _bind_cross_file_symbols(store)
    if bound:
        summary.append(f"bindings={bound}")
    if warnings:
        summary.append("warnings:")
        summary.extend(f"- {warning}" for warning in warnings[:20])
    return "\n".join(summary)
