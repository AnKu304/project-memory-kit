from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from tools.project_memory.services.context_builder import build_context
from tools.project_memory.services.doctor import doctor as doctor_service
from tools.project_memory.services.failure_memory import record_failure
from tools.project_memory.services.impact_analysis import analyze_impact, format_impact
from tools.project_memory.services.index_project import index_project
from tools.project_memory.services.knowledge import build_knowledge_context, search_knowledge, show_knowledge
from tools.project_memory.services.rationale import build_rationale_context, search_rationale, show_rationale
from tools.project_memory.services.search import search as search_service
from tools.project_memory.services.test_selector import select_tests
from tools.project_memory.version import __version__

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "project-memory-kit"

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603


def _schema(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": False,
    }


def _tool(
    name: str,
    title: str,
    description: str,
    input_schema: dict[str, Any],
    *,
    read_only: bool = True,
) -> dict[str, Any]:
    return {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": input_schema,
        "annotations": {
            "readOnlyHint": read_only,
        },
    }


TOOLS: list[dict[str, Any]] = [
    _tool(
        "pmem_doctor",
        "Project memory doctor",
        "Check local project-memory setup, migrations, vector backend, and stored memory counts.",
        _schema(),
    ),
    _tool(
        "pmem_index",
        "Index project memory",
        "Index changed files or the full project into local project memory.",
        _schema(
            {
                "mode": {
                    "type": "string",
                    "enum": ["changed", "full"],
                    "default": "changed",
                },
            }
        ),
        read_only=False,
    ),
    _tool(
        "pmem_context",
        "Build bounded task context",
        "Return bounded change context for a task: impact, retrieved chunks, knowledge, rationale, failures, and tests.",
        _schema(
            {
                "task": {"type": "string"},
                "base": {"type": "string", "default": "HEAD"},
                "reset_task": {"type": "boolean", "default": True},
            },
            ["task"],
        ),
    ),
    _tool(
        "pmem_impact",
        "Analyze change impact",
        "Return changed files, touched symbols, reverse dependencies, risk, and targeted tests.",
        _schema({"base": {"type": "string", "default": "HEAD"}}),
    ),
    _tool(
        "pmem_tests",
        "Select targeted tests",
        "Return local test commands selected from current project changes.",
        _schema({"base": {"type": "string", "default": "HEAD"}}),
    ),
    _tool(
        "pmem_search",
        "Search project memory",
        "Search local graph chunks, knowledge, or rationale and return ranked bounded results.",
        _schema(
            {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                "layer": {
                    "type": "string",
                    "enum": ["all", "knowledge", "rationale"],
                    "default": "all",
                },
            },
            ["query"],
        ),
    ),
    _tool(
        "pmem_knowledge_context",
        "Build knowledge context",
        "Return current project knowledge relevant to a task, with ids and paths to full Markdown records.",
        _schema(
            {
                "task": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 25},
            },
            ["task"],
        ),
    ),
    _tool(
        "pmem_knowledge_search",
        "Search knowledge",
        "Search current project knowledge records.",
        _schema(
            {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 5},
            },
            ["query"],
        ),
    ),
    _tool(
        "pmem_knowledge_show",
        "Show knowledge record",
        "Return the full Markdown for one project knowledge record.",
        _schema({"id": {"type": "string"}}, ["id"]),
    ),
    _tool(
        "pmem_rationale_context",
        "Build rationale context",
        "Return current rationale records relevant to a task, with ids and paths to full Markdown records.",
        _schema(
            {
                "task": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 25},
            },
            ["task"],
        ),
    ),
    _tool(
        "pmem_rationale_search",
        "Search rationale",
        "Search current rationale records for decisions, rejected paths, experiments, and evidence.",
        _schema(
            {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 5},
            },
            ["query"],
        ),
    ),
    _tool(
        "pmem_rationale_show",
        "Show rationale record",
        "Return the full Markdown for one project rationale record.",
        _schema({"id": {"type": "string"}}, ["id"]),
    ),
    _tool(
        "pmem_record_failure",
        "Record test failure",
        "Record a failure fingerprint from a local log file under project memory.",
        _schema(
            {
                "command": {"type": "string"},
                "log_file": {"type": "string"},
            },
            ["command", "log_file"],
        ),
        read_only=False,
    ),
]


def _limit(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, maximum))


def _text_result(text: str, structured: dict[str, Any] | None = None, *, is_error: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }
    if structured is not None:
        payload["structuredContent"] = structured
    return payload


def _format_search_rows(rows: list[dict[str, Any]], id_key: str | None = None) -> str:
    if not rows:
        return "No results."
    lines: list[str] = []
    for item in rows:
        path = item.get("path") or ""
        score = float(item.get("score") or 0.0)
        source = item.get("source") or "local"
        reason = item.get("reason") or "matched"
        label = item.get("fqn") or item.get(id_key or "") or item.get("title") or ""
        snippet = str(item.get("snippet") or "").replace("\n", " ").strip()
        lines.append(f"- `{path}` `{label}` [{source} {score:.2f}; {reason}]: {snippet}")
    return "\n".join(lines)


def _tool_doctor(root: Path, _: dict[str, Any]) -> dict[str, Any]:
    ok, report = doctor_service(root)
    return _text_result(report, {"ok": ok, "report": report}, is_error=not ok)


def _tool_index(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    mode = str(args.get("mode") or "changed")
    if mode not in {"changed", "full"}:
        return _text_result("mode must be `changed` or `full`.", {"mode": mode}, is_error=True)
    report = index_project(root, mode=mode)
    return _text_result(report, {"mode": mode, "report": report})


def _tool_context(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    task = str(args.get("task") or "").strip()
    if not task:
        return _text_result("task is required.", {}, is_error=True)
    base = str(args.get("base") or "HEAD")
    reset_task = bool(args.get("reset_task", True))
    context = build_context(root, task, base=base, reset_task=reset_task)
    return _text_result(context, {"task": task, "base": base, "reset_task": reset_task, "context": context})


def _tool_impact(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    base = str(args.get("base") or "HEAD")
    report = analyze_impact(root, base=base)
    return _text_result(format_impact(report, "markdown"), {"base": base, "impact": report})


def _tool_tests(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    base = str(args.get("base") or "HEAD")
    commands = select_tests(root, base=base)
    text = "\n".join(f"- `{command}`" for command in commands) if commands else "No targeted tests found."
    return _text_result(text, {"base": base, "commands": commands})


def _tool_search(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return _text_result("query is required.", {}, is_error=True)
    limit = _limit(args.get("limit"), 10, 50)
    layer = str(args.get("layer") or "all")
    if layer == "all":
        layer_arg = None
    elif layer in {"knowledge", "rationale"}:
        layer_arg = layer
    else:
        return _text_result("layer must be `all`, `knowledge`, or `rationale`.", {"layer": layer}, is_error=True)
    rows = search_service(root, query, limit, layer=layer_arg)
    return _text_result(_format_search_rows(rows), {"query": query, "limit": limit, "layer": layer, "results": rows})


def _tool_knowledge_context(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    task = str(args.get("task") or "").strip()
    if not task:
        return _text_result("task is required.", {}, is_error=True)
    limit = args.get("limit")
    context = build_knowledge_context(root, task, _limit(limit, 5, 25) if limit is not None else None)
    return _text_result(context, {"task": task, "context": context})


def _tool_knowledge_search(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return _text_result("query is required.", {}, is_error=True)
    limit = _limit(args.get("limit"), 5, 50)
    rows = search_knowledge(root, query, limit)
    return _text_result(_format_search_rows(rows, id_key="knowledge_id"), {"query": query, "limit": limit, "results": rows})


def _tool_knowledge_show(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    entry_id = str(args.get("id") or "").strip()
    if not entry_id:
        return _text_result("id is required.", {}, is_error=True)
    content = show_knowledge(root, entry_id)
    return _text_result(content, {"id": entry_id, "content": content})


def _tool_rationale_context(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    task = str(args.get("task") or "").strip()
    if not task:
        return _text_result("task is required.", {}, is_error=True)
    limit = args.get("limit")
    context = build_rationale_context(root, task, _limit(limit, 5, 25) if limit is not None else None)
    return _text_result(context, {"task": task, "context": context})


def _tool_rationale_search(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return _text_result("query is required.", {}, is_error=True)
    limit = _limit(args.get("limit"), 5, 50)
    rows = search_rationale(root, query, limit)
    return _text_result(_format_search_rows(rows, id_key="rationale_id"), {"query": query, "limit": limit, "results": rows})


def _tool_rationale_show(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    entry_id = str(args.get("id") or "").strip()
    if not entry_id:
        return _text_result("id is required.", {}, is_error=True)
    content = show_rationale(root, entry_id)
    return _text_result(content, {"id": entry_id, "content": content})


def _tool_record_failure(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    command = str(args.get("command") or "").strip()
    log_file = str(args.get("log_file") or "").strip()
    if not command or not log_file:
        return _text_result("command and log_file are required.", {}, is_error=True)
    path = Path(log_file)
    if not path.is_absolute():
        path = root / path
    fingerprint = record_failure(root, command, path)
    return _text_result(fingerprint, {"command": command, "log_file": str(path), "fingerprint": fingerprint})


ToolHandler = Callable[[Path, dict[str, Any]], dict[str, Any]]

TOOL_HANDLERS: dict[str, ToolHandler] = {
    "pmem_doctor": _tool_doctor,
    "pmem_index": _tool_index,
    "pmem_context": _tool_context,
    "pmem_impact": _tool_impact,
    "pmem_tests": _tool_tests,
    "pmem_search": _tool_search,
    "pmem_knowledge_context": _tool_knowledge_context,
    "pmem_knowledge_search": _tool_knowledge_search,
    "pmem_knowledge_show": _tool_knowledge_show,
    "pmem_rationale_context": _tool_rationale_context,
    "pmem_rationale_search": _tool_rationale_search,
    "pmem_rationale_show": _tool_rationale_show,
    "pmem_record_failure": _tool_record_failure,
}


def _response(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: Any, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}
    if data is not None:
        payload["error"]["data"] = data
    return payload


def _handle_initialize(message_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    client_version = str(params.get("protocolVersion") or "")
    protocol_version = client_version if client_version == PROTOCOL_VERSION else PROTOCOL_VERSION
    return _response(
        message_id,
        {
            "protocolVersion": protocol_version,
            "capabilities": {
                "tools": {
                    "listChanged": False,
                },
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": __version__,
            },
        },
    )


def _handle_tool_call(root: Path, message_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    if not isinstance(name, str) or not name:
        return _error(message_id, JSONRPC_INVALID_PARAMS, "tools/call requires a tool name.")
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return _error(message_id, JSONRPC_INVALID_PARAMS, f"Unknown tool: {name}")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return _error(message_id, JSONRPC_INVALID_PARAMS, "Tool arguments must be an object.")
    try:
        return _response(message_id, handler(root, arguments))
    except Exception as exc:
        return _response(message_id, _text_result(str(exc), {"error": str(exc), "tool": name}, is_error=True))


def _handle_request(root: Path, message: dict[str, Any]) -> dict[str, Any] | None:
    message_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}
    if "id" not in message:
        return None
    if not isinstance(method, str):
        return _error(message_id, JSONRPC_INVALID_REQUEST, "Request method must be a string.")
    if not isinstance(params, dict):
        return _error(message_id, JSONRPC_INVALID_PARAMS, "Request params must be an object.")

    if method == "initialize":
        return _handle_initialize(message_id, params)
    if method == "ping":
        return _response(message_id, {})
    if method == "tools/list":
        return _response(message_id, {"tools": TOOLS})
    if method == "tools/call":
        return _handle_tool_call(root, message_id, params)
    return _error(message_id, JSONRPC_METHOD_NOT_FOUND, f"Method not found: {method}")


def serve_stdio(root: Path, stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    project_root = root.resolve()

    for raw_line in input_stream:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = _error(None, JSONRPC_PARSE_ERROR, "Parse error.", {"detail": str(exc)})
        else:
            if not isinstance(message, dict):
                response = _error(None, JSONRPC_INVALID_REQUEST, "JSON-RPC message must be an object.")
            else:
                response = _handle_request(project_root, message)
        if response is None:
            continue
        output_stream.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
        output_stream.flush()
    return 0
