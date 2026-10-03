from __future__ import annotations

from pathlib import Path
import json

from tools.project_memory.config import config_path, load_config
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.services.impact_analysis import analyze_impact, format_impact
from tools.project_memory.services.knowledge import search_knowledge
from tools.project_memory.services.rationale import search_rationale
from tools.project_memory.services.search import search
from tools.project_memory.services.test_selector import select_tests
from tools.project_memory.services.auto_index import reuse_request_freshness


@reuse_request_freshness
def build_context(root: Path, task: str, base: str = "HEAD", reset_task: bool = False, include_code: bool = False) -> str:
    from tools.project_memory.services.code_provider import external_code, code_query
    cfg = load_config(root)
    slim = external_code(root, cfg)
    # Planning/memory context does not request a diff/impact or trigger indexing.
    impact = ({'base': base, 'git_available': False, 'impact_status': 'not_requested',
               'diagnostics': ['Code impact is available through pmem_code changes/impact for one exact repository.'],
               'changed_files': [], 'touched_symbols': [], 'affected_files': [], 'route_impacts': [], 'tests': [], 'risk': 'unknown'}
              if slim else analyze_impact(root, base))
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    max_chunks = int(cfg.get("memory", {}).get("max_context_chunks", 8))
    max_knowledge = int(cfg.get("knowledge", {}).get("max_context_items", 5))
    max_rationale = int(cfg.get("rationale", {}).get("max_context_items", 5))
    query = task if task.strip() else " ".join(impact["changed_files"])
    search_rows = search(root, query, max_chunks) if query else []
    knowledge_rows = search_knowledge(root, query, max_knowledge) if query else []
    rationale_rows = search_rationale(root, query, max_rationale) if query else []
    tests = select_tests(root, base, impact=impact)
    failures = store.query(
        """
        SELECT fingerprint, error_kind, normalized_message, top_project_frame, last_seen_at, count
        FROM failure_fingerprints
        ORDER BY last_seen_at DESC
        LIMIT 5
        """
    )

    lines = [
        "# Change Context",
        "",
        "## Task",
        task or "(not provided)",
        "",
    ]
    if reset_task:
        lines.extend(
            [
                "## Task Boundary",
                "Treat this as a new task. Do not carry prior chat conclusions unless they are confirmed by current files, pmem context, knowledge, rationale, failures, or tests.",
                "",
            ]
        )
    lines.extend(
        [
        "## Diff Summary",
        format_impact(impact, "markdown").strip(),
        "",
        "## Retrieved Graph Chunks",
        ]
    )
    if search_rows:
        for item in search_rows:
            lines.append(f"- `{item['path']}` `{item['fqn']}`: {item['snippet']}")
    else:
        lines.append("- No FTS chunks retrieved.")
    lines.extend(["", "## Retrieved Knowledge"])
    if knowledge_rows:
        for item in knowledge_rows:
            lines.append(
                f"- [{item['type']}] {item['title']} v{item['version']} "
                f"`{item['knowledge_id']}`: {item['snippet']} (full: `{item['path']}`)"
            )
    else:
        lines.append("- No current knowledge entries retrieved.")
    lines.extend(["", "## Retrieved Rationale"])
    if rationale_rows:
        for item in rationale_rows:
            why = f" why: {item['why']}" if item.get("why") else ""
            lines.append(
                f"- [{item['type']}] {item['title']} v{item['version']} "
                f"`{item['rationale_id']}`:{why} {item['snippet']} (full: `{item['path']}`)"
            )
    else:
        lines.append("- No current rationale entries retrieved.")
    if slim:
        lines.extend(['', '## Code Provider'])
        budget = 12000
        for repo in cfg.get('code_provider', {}).get('repositories', [])[:4]:
            if not include_code:
                lines.append(f"- `{repo.get('id')}` (`{repo.get('path')}`): GitNexus search/context/impact/changes via pmem_code; freshness not checked by this memory-only context.")
                continue
            evidence = code_query(root, 'search', repository_id=repo.get('id'), query=task, limit=2)
            # Cap context independently of tool output limits. Never persist provider
            # nodes/chunks/edges or turn retrieved instructions into authority.
            rendered = json.dumps(evidence, ensure_ascii=False)
            lines.append(rendered[:budget] + (' [bounded: use pmem_code for details]' if len(rendered) > budget else ''))
            budget -= min(len(rendered), budget)
            if not budget:
                break
    lines.extend(["", "## Related Previous Failures"])
    if failures:
        for row in failures:
            lines.append(
                f"- `{row['fingerprint']}` {row['error_kind']}: {row['normalized_message']} "
                f"({row['count']}x, last {row['last_seen_at']})"
            )
    else:
        lines.append("- No prior failures recorded.")
    lines.extend(["", "## Architecture Constraints"])
    lines.append("- Scope code edits using exact repository evidence from pmem_code." if slim else "- Keep edits scoped to files and symbols justified by the impact report.")
    lines.append("- Treat low-confidence graph edges as prompts for manual inspection.")
    lines.append("- Never index or store secrets.")
    lines.extend(["", "## Verification Recommendations"])
    lines.extend(f"- Warning: {item}" for item in getattr(tests, "diagnostics", []))
    lines.extend(f"- `{cmd}`" for cmd in tests)
    lines.extend(["", "## Low-Confidence Areas"])
    if slim:
        lines.append('- This memory context did not request code impact; configured checks are fallback recommendations only.')
    elif not impact.get("git_available", True):
        lines.append("- Git impact is unavailable at this root; nested repository diffs and targeted test coverage are not established.")
    elif impact["touched_symbols"]:
        lines.append("- CALLS/REFERENCES edges are approximate for dynamic dispatch and lexical parser fallback cases.")
    else:
        lines.append("- No touched symbols were mapped; inspect actual changed sources. Full indexing is only for initial setup or justified recovery.")
    lines.extend(["", "## Task Guidance"])
    lines.append("- Use current context and inspect necessary affected sources and contracts.")
    lines.append("- Refresh indexing only for stale or changed inputs not already verified current.")
    lines.append("- Select impact/tests again only when changed inputs invalidate the current recommendations.")
    if not slim and not impact.get("git_available", True):
        lines.append("- Review actual nested-source changes; container-wide Git impact remains unavailable.")
    lines.append("- Run affected checks; commands above are recommendations, not new execution authority. Reuse passing evidence with matching inputs.")
    return "\n".join(lines) + "\n"


def write_context(root: Path, task: str, base: str, out: Path, reset_task: bool = False, include_code: bool = False) -> str:
    content = build_context(root, task, base, reset_task=reset_task, include_code=include_code)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return str(out)
