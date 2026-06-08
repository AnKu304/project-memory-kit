from __future__ import annotations

from pathlib import Path

from tools.project_memory.config import load_config
from tools.project_memory.services.impact_analysis import analyze_impact, format_impact
from tools.project_memory.services.knowledge import search_knowledge
from tools.project_memory.services.local_evidence import format_local_evidence, local_evidence
from tools.project_memory.services.memory_lifecycle import format_lifecycle, lifecycle_report
from tools.project_memory.services.rationale import search_rationale
from tools.project_memory.services.search import search
from tools.project_memory.services.task_gate import format_gate, gate_report
from tools.project_memory.services.test_selector import select_tests


def _fmt_components(item: dict[str, object]) -> str:
    components = item.get("components")
    if not components:
        return "{}"
    return "{" + ", ".join(f"{key}={value}" for key, value in dict(components).items()) + "}"


def _graph_lines(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return ["- No graph chunks retrieved."]
    lines = []
    for item in rows:
        lines.append(
            f"- `{item['path']}` `{item.get('fqn', '')}` score={float(item.get('score') or 0.0):.2f}: "
            f"{item.get('snippet', '')} "
            f"(why: {item.get('reason', 'matched')}; components: {_fmt_components(item)})"
        )
    return lines


def _knowledge_lines(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return ["- No current knowledge entries retrieved."]
    return [
        f"- [{item['type']}] {item['title']} v{item['version']} `{item['knowledge_id']}`: "
        f"{item['snippet']} (source: `{item['path']}`; status={item['status']})"
        for item in rows
    ]


def _rationale_lines(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return ["- No current rationale entries retrieved."]
    lines = []
    for item in rows:
        evidence = ", ".join(str(value) for value in item.get("evidence", [])[:3]) or "not recorded"
        why = f" why: {item['why']}" if item.get("why") else ""
        lines.append(
            f"- [{item['type']}] {item['title']} v{item['version']} `{item['rationale_id']}`:{why} "
            f"{item['snippet']} (source: `{item['path']}`; evidence: {evidence})"
        )
    return lines


def compile_context(root: Path, task: str, base: str = "HEAD", reset_task: bool = False) -> str:
    cfg = load_config(root)
    impact = analyze_impact(root, base)
    evidence = local_evidence(root, base)
    lifecycle = lifecycle_report(root)
    query = task.strip() or " ".join(impact["changed_files"])
    max_chunks = int(cfg.get("memory", {}).get("max_context_chunks", 8))
    max_knowledge = int(cfg.get("knowledge", {}).get("max_context_items", 5))
    max_rationale = int(cfg.get("rationale", {}).get("max_context_items", 5))
    graph_rows = search(root, query, max_chunks, debug=True) if query else []
    knowledge_rows = search_knowledge(root, query, max_knowledge) if query else []
    rationale_rows = search_rationale(root, query, max_rationale) if query else []
    tests = select_tests(root, base)
    pre_gate = gate_report(evidence, impact, "pre")
    post_gate = gate_report(evidence, impact, "post")

    lines = ["# Compiled Project Context", "", "## Task", task or "(not provided)", ""]
    if reset_task:
        lines.extend(
            [
                "## Task Boundary",
                "Treat this as a new task. Use only current local files, project memory, tests, and evidence.",
                "",
            ]
        )
    lines.extend(["## Inclusion Reasons"])
    lines.append("- Impact is included to keep edits scoped to changed and affected files.")
    lines.append("- Search results are included for nearby code and memory with ranking reasons.")
    lines.append("- Knowledge/rationale are included only as current durable context.")
    lines.append("- Local evidence is included to avoid loading large logs or files into model context.")
    lines.append("")
    lines.extend(["## Local Evidence", format_local_evidence(evidence).strip(), ""])
    lines.extend(["## Preflight Gate", format_gate(pre_gate).strip(), ""])
    lines.extend(["## Impact", format_impact(impact, "markdown").strip(), ""])
    lines.extend(["## Retrieved Graph Chunks", *_graph_lines(graph_rows), ""])
    lines.extend(["## Retrieved Knowledge", *_knowledge_lines(knowledge_rows), ""])
    lines.extend(["## Retrieved Rationale", *_rationale_lines(rationale_rows), ""])
    lines.extend(["## Memory Lifecycle", format_lifecycle(lifecycle).strip(), ""])
    lines.extend(["## Verification Commands"])
    lines.extend(f"- `{command}`" for command in tests)
    lines.extend(["", "## Postflight Gate", format_gate(post_gate).strip(), ""])
    lines.extend(["## Provenance"])
    lines.append("- impact: git diff plus local dependency graph")
    lines.append("- graph chunks: SQLite FTS/vector/local graph rows")
    lines.append("- knowledge: `.project-memory/knowledge/**/*.md` current records")
    lines.append("- rationale: `.project-memory/rationale/**/*.md` current records with evidence")
    lines.append("- failures: `.project-memory/graph.sqlite` failure fingerprints")
    lines.append("- tests: local impact analysis and project config")
    return "\n".join(lines) + "\n"


def write_compiled_context(root: Path, task: str, base: str, out: Path, reset_task: bool = False) -> str:
    content = compile_context(root, task, base=base, reset_task=reset_task)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return str(out)
