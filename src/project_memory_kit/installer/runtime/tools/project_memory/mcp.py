from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from tools.project_memory.services.context_builder import build_context
from tools.project_memory.services.doctor import doctor as doctor_service
from tools.project_memory.services.eval_runner import format_eval, run_eval
from tools.project_memory.services.failure_memory import record_failure
from tools.project_memory.services.governance import audit_project, format_audit
from tools.project_memory.services.human import (
    export_human,
    format_human_export,
    format_human_graph,
    format_human_search,
    format_human_status,
    human_graph,
    human_status,
    search_human,
)
from tools.project_memory.services.impact_analysis import analyze_impact, format_impact
from tools.project_memory.services.index_project import index_project
from tools.project_memory.services.knowledge import build_knowledge_context, search_knowledge, show_knowledge
from tools.project_memory.services.modules import format_module_states, module_states
from tools.project_memory.services.rationale import build_rationale_context, search_rationale, show_rationale
from tools.project_memory.services.search import search as search_service
from tools.project_memory.services.status import format_stale, format_status, project_status
from tools.project_memory.services.tasks import format_tasks, list_tasks
from tools.project_memory.services.test_selector import explain_tests, select_tests
from tools.project_memory.mcp_tools import TOOLS
from tools.project_memory.version import __version__

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "project-memory-kit"

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603

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


def _tool_status(root: Path, _: dict[str, Any]) -> dict[str, Any]:
    report = project_status(root)
    return _text_result(format_status(report), {"status": report})


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
    if bool(args.get("explain", False)):
        text = explain_tests(root, base=base)
        return _text_result(text, {"base": base, "explain": text})
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
    elif layer in {"knowledge", "rationale", "human"}:
        layer_arg = layer
    else:
        return _text_result("layer must be `all`, `knowledge`, `rationale`, or `human`.", {"layer": layer}, is_error=True)
    rows = search_service(root, query, limit, layer=layer_arg)
    return _text_result(_format_search_rows(rows), {"query": query, "limit": limit, "layer": layer, "results": rows})


def _tool_search_debug(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return _text_result("query is required.", {}, is_error=True)
    limit = _limit(args.get("limit"), 10, 50)
    layer = str(args.get("layer") or "all")
    layer_arg = None if layer == "all" else layer
    if layer_arg not in {None, "knowledge", "rationale", "human"}:
        return _text_result("layer must be `all`, `knowledge`, `rationale`, or `human`.", {"layer": layer}, is_error=True)
    rows = search_service(root, query, limit, layer=layer_arg, debug=True)
    text = _format_search_rows(rows)
    if rows:
        text += "\n" + "\n".join(f"  components: {item.get('components', {})}" for item in rows)
    return _text_result(text, {"query": query, "limit": limit, "layer": layer, "results": rows})


def _tool_eval(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    raw_file = str(args.get("file") or "").strip()
    file_path = None
    if raw_file:
        file_path = Path(raw_file)
        if not file_path.is_absolute():
            file_path = root / file_path
    limit = _limit(args.get("limit"), 10, 50)
    report = run_eval(root, file_path=file_path, limit=limit)
    return _text_result(format_eval(report), {"eval": report}, is_error=int(report["failed"]) > 0)


def _tool_audit(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    report = audit_project(root, include_secrets=bool(args.get("secrets")))
    return _text_result(format_audit(report), {"audit": report}, is_error=not bool(report["ok"]))


def _tool_modules(root: Path, _: dict[str, Any]) -> dict[str, Any]:
    states = [
        {
            "name": state.name,
            "enabled": state.enabled,
            "path_key": state.path_key,
            "path": str(state.path) if state.path else None,
            "description": state.description,
        }
        for state in module_states(root)
    ]
    return _text_result(format_module_states(root), {"modules": states})


def _tool_watch_status(root: Path, _: dict[str, Any]) -> dict[str, Any]:
    report = project_status(root)
    return _text_result(format_stale(root), {"index": report["index"]})


def _tool_tasks(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    role = str(args.get("role") or "").strip() or None
    include_closed = bool(args.get("all"))
    tasks = list_tasks(root, include_closed=include_closed, role=role)
    return _text_result(format_tasks(tasks), {"tasks": [item.__dict__ for item in tasks]})


def _tool_human_status(root: Path, _: dict[str, Any]) -> dict[str, Any]:
    status = human_status(root)
    return _text_result(format_human_status(status), {"human": status})


def _tool_human_export(root: Path, _: dict[str, Any]) -> dict[str, Any]:
    report = export_human(root)
    return _text_result(format_human_export(report), {"human": report.__dict__})


def _tool_human_search(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return _text_result("query is required.", {}, is_error=True)
    limit = _limit(args.get("limit"), 10, 50)
    rows = search_human(root, query, limit=limit)
    return _text_result(format_human_search(rows), {"query": query, "limit": limit, "results": rows})


def _tool_human_graph(root: Path, _: dict[str, Any]) -> dict[str, Any]:
    report = human_graph(root)
    return _text_result(format_human_graph(report), {"human_graph": report.__dict__})


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
    "pmem_status": _tool_status,
    "pmem_context": _tool_context,
    "pmem_impact": _tool_impact,
    "pmem_tests": _tool_tests,
    "pmem_search": _tool_search,
    "pmem_search_debug": _tool_search_debug,
    "pmem_eval": _tool_eval,
    "pmem_audit": _tool_audit,
    "pmem_modules": _tool_modules,
    "pmem_watch_status": _tool_watch_status,
    "pmem_tasks": _tool_tasks,
    "pmem_human_status": _tool_human_status,
    "pmem_human_export": _tool_human_export,
    "pmem_human_search": _tool_human_search,
    "pmem_human_graph": _tool_human_graph,
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
