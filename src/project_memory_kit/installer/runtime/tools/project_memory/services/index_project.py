from __future__ import annotations

import json
from pathlib import Path

from tools.project_memory.config import config_path, load_config
from tools.project_memory.git_diff import changed_files, untracked_files
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.hashing import sha256_file
from tools.project_memory.ignore import iter_indexable_files
from tools.project_memory.parsers.js_ts import JsTsParser
from tools.project_memory.parsers.js_ts_imports import JS_TS_EXTENSIONS, language_for_path as js_ts_language_for_path
from tools.project_memory.parsers.python_ast import PythonAstParser
from tools.project_memory.parsers.symbol_model import ParseResult, Symbol
from tools.project_memory.services.next_graph import (
    bind_next_route_components,
    file_properties,
    is_route_component_symbol,
    next_route_info,
)
from tools.project_memory.vector.qdrant_store import QdrantLocalStore


PYTHON_PARSER = PythonAstParser()
JS_TS_PARSER = JsTsParser()


def _iter_files(root: Path, mode: str, store: SQLiteGraphStore | None = None) -> list[Path]:
    all_files = iter_indexable_files(root)
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
    current_paths = {path.relative_to(root).as_posix() for path in iter_indexable_files(root)}
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
    route_id: str | None = None,
    route_info: dict[str, object] | None = None,
    component_boundary: str | None = None,
) -> list[str]:
    module_id = store.upsert_node(kind="Module", name=result.module, fqn=result.module, path=rel, language=language)
    store.upsert_edge(file_id, module_id, "DEFINES", evidence=rel)

    symbol_ids: dict[str, str] = {}
    for symbol in result.symbols:
        properties = {
            "kind": symbol.kind,
            "signature": symbol.signature,
            "docstring": symbol.docstring,
            "decorators": symbol.decorators,
            "bases": symbol.bases,
            "calls": symbol.calls,
            "references": symbol.references,
        }
        if component_boundary:
            properties["component_boundary"] = component_boundary
        symbol_id = store.upsert_node(
            kind="Symbol",
            name=symbol.name,
            fqn=symbol.fqn,
            path=rel,
            language=language,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            properties=properties,
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

    if route_id and route_info:
        for symbol in result.symbols:
            symbol_id = symbol_ids.get(symbol.fqn)
            if symbol_id and is_route_component_symbol(symbol, route_info):
                store.upsert_edge(
                    route_id,
                    symbol_id,
                    "ROUTE_COMPONENT",
                    source="next_route",
                    confidence=0.9,
                    evidence=symbol.fqn,
                    properties={"route": route_info.get("route"), "boundary": component_boundary},
                )

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


def _source_candidates_for_test(path: str) -> list[str]:
    source = Path(path)
    name = source.name
    parent = source.parent
    candidates: list[Path] = []
    if name.startswith("test_") and source.suffix == ".py":
        candidates.append(Path("src") / f"{name[5:]}")
        candidates.append(parent.parent / f"{name[5:]}")
    for marker in [".test", ".spec"]:
        if marker in source.stem:
            base = source.stem.split(marker, 1)[0] + source.suffix
            candidates.extend([parent / base, parent.parent / base, Path("src") / base])
    if "__tests__" in source.parts:
        parts = list(source.parts)
        index = parts.index("__tests__")
        candidates.append(Path(*parts[:index], parts[-1].replace(".test", "").replace(".spec", "")))
    return [candidate.as_posix() for candidate in candidates if candidate.as_posix() != path]


def _bind_test_files(store: SQLiteGraphStore) -> int:
    test_rows = store.query(
        """
        SELECT id, path
        FROM nodes
        WHERE kind = 'File' AND (
          path LIKE 'tests/%' OR path LIKE '%/__tests__/%'
          OR path LIKE '%.test.%' OR path LIKE '%.spec.%'
        )
        """
    )
    bound = 0
    for test in test_rows:
        for candidate in _source_candidates_for_test(str(test["path"])):
            source_rows = store.query("SELECT id FROM nodes WHERE kind = 'File' AND path = ?", (candidate,))
            for source in source_rows:
                store.upsert_edge(
                    test["id"],
                    source["id"],
                    "TESTS",
                    source="test_binding",
                    confidence=0.72,
                    evidence=str(test["path"]),
                )
                bound += 1
    return bound


def _index_text_file(
    path: Path,
    rel: str,
    file_id: str,
    file_hash: str,
    store: SQLiteGraphStore,
    vectors: QdrantLocalStore,
) -> None:
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


def _index_file(
    root: Path,
    path: Path,
    mode: str,
    project_id: str,
    store: SQLiteGraphStore,
    vectors: QdrantLocalStore,
) -> tuple[bool, bool, list[str]]:
    rel = path.relative_to(root).as_posix()
    file_hash = sha256_file(path)
    if mode == "changed" and store.file_hash(rel) == file_hash:
        return False, True, []

    store.clear_generated_file_memory(rel)
    parser, language, parser_name = _parser_for(path)
    route_info = next_route_info(path, rel)
    file_props = file_properties(path, rel, route_info)
    file_id = store.upsert_node(
        kind="File",
        name=path.name,
        fqn=rel,
        path=rel,
        language=language,
        hash=file_hash,
        properties=file_props,
    )
    store.upsert_edge(project_id, file_id, "CONTAINS", evidence=rel)
    route_id = _index_route_node(store, file_id, rel, language, route_info)

    if parser is None:
        _index_text_file(path, rel, file_id, file_hash, store, vectors)
        return True, False, []

    result = parser.parse(root, path)
    warnings = _index_parse_result(
        path,
        rel,
        file_id,
        file_hash,
        language or "text",
        parser_name,
        result,
        store,
        vectors,
        route_id=route_id,
        route_info=route_info,
        component_boundary=str(file_props.get("component_boundary")) if file_props.get("component_boundary") else None,
    )
    return True, False, warnings


def _index_route_node(
    store: SQLiteGraphStore,
    file_id: str,
    rel: str,
    language: str | None,
    route_info: dict[str, object] | None,
) -> str | None:
    if not route_info:
        return None
    route_id = store.upsert_node(
        kind="Route",
        name=route_info["route"],
        fqn=f"next:{route_info['route_kind']}:{route_info['route']}",
        path=rel,
        language=language,
        layer="frontend",
        properties=route_info,
    )
    store.upsert_edge(file_id, route_id, "DEFINES", confidence=0.9, evidence=str(route_info["route"]))
    return route_id


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
        url=vector_cfg.get("url"),
        root=root,
    )

    try:
        files = _iter_files(root, mode, store)
        indexed = 0
        skipped = 0
        warnings: list[str] = []
        removed = _cleanup_removed_files(root, store)

        project_id = store.upsert_node(kind="Project", name=root.name, fqn=root.name, path=".")

        for path in files:
            did_index, did_skip, file_warnings = _index_file(root, path, mode, project_id, store, vectors)
            if did_skip:
                skipped += 1
            if did_index:
                indexed += 1
            warnings.extend(file_warnings)
    finally:
        vectors.close()

    summary = [f"indexed={indexed}", f"skipped={skipped}", f"removed={removed}", f"mode={mode}"]
    bound = _bind_cross_file_symbols(store)
    if bound:
        summary.append(f"bindings={bound}")
    test_bound = _bind_test_files(store)
    if test_bound:
        summary.append(f"test_bindings={test_bound}")
    route_bound = bind_next_route_components(store)
    if route_bound:
        summary.append(f"route_bindings={route_bound}")
    if warnings:
        summary.append("warnings:")
        summary.extend(f"- {warning}" for warning in warnings[:20])
    return "\n".join(summary)
