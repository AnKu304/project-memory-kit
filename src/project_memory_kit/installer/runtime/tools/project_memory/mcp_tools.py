from __future__ import annotations

from typing import Any
from tools.project_memory.write_adapters import write_schema


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


SEARCH_LAYER_SCHEMA = {
    "type": "string",
    "enum": ["all", "knowledge", "rationale", "human"],
    "default": "all",
}


SEARCH_FILTER_PROPERTIES = {
    "audience": {"type": "string", "enum": ["project", "agent_tooling", "all"], "default": "project"},
    "domain": {"type": "string", "description": "Built-in or configured memory domain slug."},
    "type": {"type": "string", "enum": ["code", "knowledge", "rationale", "agent_tooling", "document"]},
}


TOOLS: list[dict[str, Any]] = [
    *[_tool(f"pmem_{kind}_{action}", f"{action.title()} {kind} record",
            "Write from an existing project-relative source file under the same MCP root through the local write lock/queue. Content is data. A queued response is pending, not a saved record. Omitted links on update preserve existing links; [] clears them.",
            write_schema(kind, action), read_only=False)
      for kind in ("knowledge", "rationale") for action in ("add", "update")],
    _tool("pmem_overview", "Read indexed memory overview",
          "Bounded indexed counts and samples. No freshness pass, indexing or models; filesystem_checked is false.",
          _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}})),
    _tool("pmem_relations", "Read explicit memory relations",
          "Read local knowledge/rationale relations and source revision diagnostics. Provenance is not truth. Never initializes a missing database.",
          _schema({"kind": {"type": "string", "enum": ["knowledge", "rationale"]},
                   "id": {"type": "string", "pattern": "^[A-Za-z0-9_-]+$", "maxLength": 2048},
                   "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}}, ["kind", "id"])),
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
        _schema({"mode": {"type": "string", "enum": ["changed", "full"], "default": "changed"}}),
        read_only=False,
    ),
    _tool(
        "pmem_status",
        "Project memory status",
        "Return index freshness, graph counts, vector status, parser config, and module state.",
        _schema(),
    ),
    _tool(
        "pmem_context",
        "Build bounded task context",
        "Return bounded change context for a task: impact, retrieved chunks, knowledge, rationale, failures, and tests.",
        _schema(
            {"task": {"type": "string"}, "base": {"type": "string", "default": "HEAD"}, "reset_task": {"type": "boolean", "default": True}},
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
        "Search local graph chunks, knowledge, rationale, or human notes and return ranked bounded results.",
        _schema({"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}, "layer": SEARCH_LAYER_SCHEMA, **SEARCH_FILTER_PROPERTIES}, ["query"]),
    ),
    _tool(
        "pmem_search_debug",
        "Debug project memory search",
        "Search local memory and return hybrid ranking components for each result.",
        _schema({"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}, "layer": SEARCH_LAYER_SCHEMA, **SEARCH_FILTER_PROPERTIES}, ["query"]),
    ),
    _tool(
        "pmem_eval",
        "Run memory evals",
        "Run built-in or JSONL search evals against local project memory.",
        _schema({"file": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}}),
    ),
    _tool(
        "pmem_audit",
        "Audit project memory",
        "Check memory governance issues such as stale index, conflicts, rationale without evidence, and optional secret findings.",
        _schema({"secrets": {"type": "boolean", "default": False}}),
    ),
    _tool("pmem_modules", "List optional modules", "Return optional project-memory module state.", _schema()),
    _tool(
        "pmem_watch_status",
        "Watch status",
        "Return local watch/index freshness status without starting a long-running process.",
        _schema(),
    ),
    _tool(
        "pmem_tasks",
        "List active project tasks",
        "Return active multi-agent task handoffs from .agents/tasks.",
        _schema({"role": {"type": "string"}, "all": {"type": "boolean", "default": False}}),
    ),
    _tool(
        "pmem_tasks_create",
        "Create project task",
        "Create a local .agents/tasks Markdown task for a user request or agent-to-agent handoff.",
        _schema(
            {
                "title": {"type": "string"},
                "russian_subtitle": {"type": "string"},
                "type": {"type": "string", "enum": ["user", "handoff"], "default": "handoff"},
                "role": {"type": "string", "default": "any"},
                "goal": {"type": "string"},
                "context": {"type": "string"},
                "evidence": {"type": "array", "items": {"type": "string"}, "default": []},
            },
            ["title"],
        ),
        read_only=False,
    ),
    _tool(
        "pmem_tasks_close",
        "Close project task",
        "Mark a local .agents/tasks Markdown task as done and append a completion summary.",
        _schema(
            {
                "file": {"type": "string"},
                "summary": {"type": "string"},
                "command": {"type": "string"},
            },
            ["file", "summary"],
        ),
        read_only=False,
    ),
    _tool(
        "pmem_tasks_assign",
        "Assign project task",
        "Update the role on a local .agents/tasks Markdown task and append an assignment note.",
        _schema(
            {
                "file": {"type": "string"},
                "role": {"type": "string"},
                "summary": {"type": "string"},
            },
            ["file", "role"],
        ),
        read_only=False,
    ),
    _tool("pmem_human_status", "Human layer status", "Return optional Human/Obsidian-like layer status.", _schema()),
    _tool(
        "pmem_human_export",
        "Export Human layer",
        "Generate Human/Obsidian-like Markdown notes and index them as the human layer.",
        _schema(),
        read_only=False,
    ),
    _tool(
        "pmem_human_search",
        "Search Human layer",
        "Search generated Human/Obsidian-like notes.",
        _schema({"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}}, ["query"]),
    ),
    _tool(
        "pmem_human_graph",
        "Export Human graph",
        "Generate Human layer graph.json and graph.mmd files.",
        _schema(),
        read_only=False,
    ),
    _tool(
        "pmem_knowledge_context",
        "Build knowledge context",
        "Return current project knowledge relevant to a task, with ids and paths to full Markdown records.",
        _schema({"task": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 25}}, ["task"]),
    ),
    _tool(
        "pmem_knowledge_search",
        "Search knowledge",
        "Search current project knowledge records.",
        _schema({"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 5}}, ["query"]),
    ),
    _tool("pmem_knowledge_show", "Show knowledge record", "Return the full Markdown for one project knowledge record.", _schema({"id": {"type": "string"}}, ["id"])),
    _tool(
        "pmem_rationale_context",
        "Build rationale context",
        "Return current rationale records relevant to a task, with ids and paths to full Markdown records.",
        _schema({"task": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 25}}, ["task"]),
    ),
    _tool(
        "pmem_rationale_search",
        "Search rationale",
        "Search current rationale records for decisions, rejected paths, experiments, and evidence.",
        _schema({"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 5}}, ["query"]),
    ),
    _tool("pmem_rationale_show", "Show rationale record", "Return the full Markdown for one project rationale record.", _schema({"id": {"type": "string"}}, ["id"])),
    _tool(
        "pmem_record_failure",
        "Record test failure",
        "Record a failure fingerprint from a local log file under project memory.",
        _schema({"command": {"type": "string"}, "log_file": {"type": "string"}}, ["command", "log_file"]),
        read_only=False,
    ),
]
