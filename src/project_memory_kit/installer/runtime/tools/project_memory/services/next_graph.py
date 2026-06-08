from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.parsers.js_ts_imports import JS_TS_EXTENSIONS
from tools.project_memory.parsers.symbol_model import Symbol


NEXT_ROUTE_FILES = {"page", "layout", "route", "loading", "error", "not-found", "template", "default"}
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


def _top_level_directive(source: str) -> str | None:
    for line in source.splitlines()[:12]:
        stripped = line.strip().rstrip(";")
        if not stripped or stripped.startswith("//"):
            continue
        if stripped in {"'use client'", '"use client"'}:
            return "use client"
        if stripped in {"'use server'", '"use server"'}:
            return "use server"
        break
    return None


def component_boundary(path: Path, rel: str) -> str | None:
    if path.suffix not in JS_TS_EXTENSIONS:
        return None
    try:
        directive = _top_level_directive(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        directive = None
    if directive == "use client":
        return "client"
    if directive == "use server":
        return "server"
    parts = Path(rel).parts
    return "server" if "app" in parts and path.stem in NEXT_ROUTE_FILES else None


def _route_http_methods(path: Path) -> list[str]:
    if path.stem != "route":
        return []
    source = path.read_text(encoding="utf-8", errors="replace")
    found = set(re.findall(r"\bexport\s+(?:async\s+)?function\s+([A-Z]+)\s*\(", source))
    found.update(re.findall(r"\bexport\s+const\s+([A-Z]+)\s*=", source))
    return sorted(method for method in found if method in HTTP_METHODS)


def next_route_info(path: Path, rel: str) -> dict[str, object] | None:
    if path.suffix not in JS_TS_EXTENSIONS or path.stem not in NEXT_ROUTE_FILES:
        return None
    parts = Path(rel).parts
    try:
        app_index = parts.index("app")
    except ValueError:
        return None
    route_parts = [part for part in parts[app_index + 1 : -1] if not (part.startswith("(") and part.endswith(")"))]
    route = "/" + "/".join(route_parts)
    if route != "/":
        route = route.rstrip("/")
    route_kind = "api_route" if path.stem == "route" else "page_route"
    return {
        "framework": "next",
        "route": route,
        "route_kind": route_kind,
        "route_file": path.name,
        "component_boundary": component_boundary(path, rel) or "server",
        "http_methods": _route_http_methods(path),
    }


def file_properties(path: Path, rel: str, route_info: dict[str, object] | None) -> dict[str, object]:
    props: dict[str, object] = {}
    boundary = str(route_info.get("component_boundary")) if route_info else component_boundary(path, rel)
    if boundary and boundary != "None":
        props["component_boundary"] = boundary
    if route_info:
        props["framework"] = "next"
        props["route"] = route_info["route"]
        props["route_kind"] = route_info["route_kind"]
    return props


def is_route_component_symbol(symbol: Symbol, route_info: dict[str, object]) -> bool:
    if str(route_info.get("route_kind") or "") == "api_route":
        return symbol.name in set(route_info.get("http_methods") or [])
    stem = Path(str(route_info.get("route_file") or "")).stem
    expected = {
        "page": {"default", "Page"},
        "layout": {"default", "Layout"},
        "loading": {"default", "Loading"},
        "error": {"default", "Error"},
        "not-found": {"default", "NotFound", "NotFoundPage"},
        "template": {"default", "Template"},
        "default": {"default", "Default"},
    }.get(stem, {"default"})
    return symbol.name in expected


def bind_next_route_components(store: SQLiteGraphStore) -> int:
    routes = store.query("SELECT id, name, path FROM nodes WHERE kind = 'Route'")
    bound = 0
    for route in routes:
        rows = store.query(
            """
            SELECT DISTINCT dst.id, dst.fqn, src.fqn AS via, e.kind
            FROM nodes src
            JOIN edges e ON e.src_id = src.id
            JOIN nodes dst ON dst.id = e.dst_id
            WHERE src.kind = 'Symbol'
              AND src.path = ?
              AND e.kind IN ('CALLS', 'REFERENCES')
              AND dst.kind = 'Symbol'
            """,
            (route["path"],),
        )
        for row in rows:
            if not row["id"]:
                continue
            store.upsert_edge(
                route["id"],
                row["id"],
                "ROUTE_COMPONENT",
                source="next_route_binding",
                confidence=0.75,
                evidence=f"{route['name']} via {row['via']}",
                properties={"via": row["via"], "edge_kind": row["kind"]},
            )
            bound += 1
    return bound
