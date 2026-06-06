from __future__ import annotations

from pathlib import Path

from tools.project_memory.config import config_path, load_config
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.services.impact_analysis import analyze_impact, format_impact
from tools.project_memory.services.knowledge import search_knowledge
from tools.project_memory.services.search import search
from tools.project_memory.services.test_selector import select_tests


def build_context(root: Path, task: str, base: str = "HEAD") -> str:
    impact = analyze_impact(root, base)
    store = SQLiteGraphStore(root, config_path(root, "graph_db"))
    store.initialize()
    cfg = load_config(root)
    max_chunks = int(cfg.get("memory", {}).get("max_context_chunks", 8))
    max_knowledge = int(cfg.get("knowledge", {}).get("max_context_items", 5))
    query = task if task.strip() else " ".join(impact["changed_files"])
    search_rows = search(root, query, max_chunks) if query else []
    knowledge_rows = search_knowledge(root, query, max_knowledge) if query else []
    tests = select_tests(root, base)
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
        "## Diff Summary",
        format_impact(impact, "markdown").strip(),
        "",
        "## Retrieved Graph Chunks",
    ]
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
    lines.append("- Keep edits scoped to files and symbols justified by the impact report.")
    lines.append("- Treat low-confidence graph edges as prompts for manual inspection.")
    lines.append("- Never index or store secrets.")
    lines.extend(["", "## Verification Commands"])
    lines.extend(f"- `{cmd}`" for cmd in tests)
    lines.extend(["", "## Low-Confidence Areas"])
    if impact["touched_symbols"]:
        lines.append("- CALLS/REFERENCES edges are approximate for dynamic dispatch and lexical parser fallback cases.")
    else:
        lines.append("- No touched symbols were mapped; run a full index or inspect the changed files manually.")
    lines.extend(["", "## Agent Checklist"])
    lines.append("- [ ] Read this file before editing.")
    lines.append("- [ ] Inspect affected files and tests.")
    lines.append("- [ ] Make the smallest viable change.")
    lines.append("- [ ] Re-run `./pmem index --mode changed`.")
    lines.append("- [ ] Re-run `./pmem impact --base HEAD --format markdown`.")
    lines.append("- [ ] Run targeted tests.")
    return "\n".join(lines) + "\n"


def write_context(root: Path, task: str, base: str, out: Path) -> str:
    content = build_context(root, task, base)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return str(out)
