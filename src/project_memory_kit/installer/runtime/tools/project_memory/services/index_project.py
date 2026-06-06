from __future__ import annotations

from pathlib import Path

from tools.project_memory.config import config_path, load_config
from tools.project_memory.git_diff import changed_files
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.hashing import sha256_file
from tools.project_memory.ignore import should_index
from tools.project_memory.parsers.python_ast import PythonAstParser
from tools.project_memory.vector.qdrant_store import QdrantLocalStore


def _iter_files(root: Path, mode: str) -> list[Path]:
    if mode == "changed":
        changed = changed_files(root)
        if changed:
            return [root / item for item in changed if (root / item).exists()]
    return [path for path in root.rglob("*") if should_index(root, path)]


def _lines_for(path: Path, start_line: int, end_line: int) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[max(start_line - 1, 0) : end_line])


def index_project(root: Path, mode: str = "changed") -> str:
    cfg = load_config(root)
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    vectors = QdrantLocalStore(config_path(root, "qdrant_path"), cfg.get("memory", {}).get("vector_size", 64))
    parser = PythonAstParser()

    files = [path for path in _iter_files(root, mode) if should_index(root, path)]
    indexed = 0
    skipped = 0
    warnings: list[str] = []

    project_id = store.upsert_node(kind="Project", name=root.name, fqn=root.name, path=".")

    for path in files:
        rel = path.relative_to(root).as_posix()
        file_hash = sha256_file(path)
        if mode == "changed" and store.file_hash(rel) == file_hash:
            skipped += 1
            continue

        store.clear_generated_file_memory(rel)
        file_id = store.upsert_node(
            kind="File",
            name=path.name,
            fqn=rel,
            path=rel,
            language="python" if path.suffix == ".py" else None,
            hash=file_hash,
        )
        store.upsert_edge(project_id, file_id, "CONTAINS", evidence=rel)

        if path.suffix == ".py":
            result = parser.parse(root, path)
            module_id = store.upsert_node(kind="Module", name=result.module, fqn=result.module, path=rel, language="python")
            store.upsert_edge(file_id, module_id, "DEFINES", evidence=rel)

            symbol_ids: dict[str, str] = {}
            for symbol in result.symbols:
                symbol_id = store.upsert_node(
                    kind="Symbol",
                    name=symbol.name,
                    fqn=symbol.fqn,
                    path=rel,
                    language="python",
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                    properties={
                        "kind": symbol.kind,
                        "signature": symbol.signature,
                        "docstring": symbol.docstring,
                        "decorators": symbol.decorators,
                        "bases": symbol.bases,
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
                for call in symbol.calls:
                    target = next((sid for fqn, sid in symbol_ids.items() if fqn.endswith("." + call) or fqn.endswith(call)), None)
                    if target:
                        store.upsert_edge(symbol_id, target, "CALLS", confidence=0.55, evidence=call)
                for base in symbol.bases:
                    target = next((sid for fqn, sid in symbol_ids.items() if fqn.endswith("." + base) or fqn.endswith(base)), None)
                    if target:
                        store.upsert_edge(symbol_id, target, "INHERITS", confidence=0.65, evidence=base)

            for item in result.imports:
                if item.target_path:
                    target_id = store.upsert_node(
                        kind="File",
                        name=Path(item.target_path).name,
                        fqn=item.target_path,
                        path=item.target_path,
                        language="python",
                    )
                    store.upsert_edge(file_id, target_id, "IMPORTS", confidence=0.85, evidence=item.module)
            warnings.extend(f"{rel}: {warning}" for warning in result.warnings)
            store.update_file_state(rel, file_hash, "python_ast", result.warnings)
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

    summary = [f"indexed={indexed}", f"skipped={skipped}", f"mode={mode}"]
    if warnings:
        summary.append("warnings:")
        summary.extend(f"- {warning}" for warning in warnings[:20])
    return "\n".join(summary)

