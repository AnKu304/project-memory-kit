## Local Project Memory Protocol

This repository uses local Dependency Graph RAG project memory.

The memory system is installed in:

```text
.project-memory/
tools/project_memory/
.agents/skills/dependency-graph-rag/
.agents/rules/
```

If the local MCP server is configured, use the equivalent `pmem_*` tools for bounded context, search, impact, tests, knowledge, and rationale. The CLI commands below remain the fallback and verification baseline.

Before any meaningful code, config, schema, dependency, API, test, build, routing, migration, auth, persistence, or architecture change, run:

```bash
./pmem doctor
./pmem status
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "<current task>" --base HEAD --reset-task --out .project-memory/reports/CHANGE_CONTEXT.md
```

Read `.project-memory/reports/CHANGE_CONTEXT.md` before editing. Identify target files, target symbols, direct dependencies, reverse dependencies, affected tests, related previous failures, architecture constraints, and low-confidence graph areas.

If `.agents/tasks/` exists, check active user tasks and handoffs before starting:

```bash
./pmem tasks check
```

Keep context bounded. Use local tools to inspect large files, logs, reports, and test output. Bring only relevant findings, short excerpts, ids, and paths into the working context. Open full files, full knowledge/rationale notes, or long logs only when local summaries are insufficient.

For research, product, UX, design, SEO, architecture, content, positioning, or other principle-heavy work, also run:

```bash
./pmem knowledge context --task "<current task>" --out .project-memory/reports/KNOWLEDGE_CONTEXT.md
```

Read `.project-memory/reports/KNOWLEDGE_CONTEXT.md` and open the referenced full Markdown files before relying on a research note or project principle.

For tasks involving "why", rejected approaches, architecture choices, storage choices, tool choices, prior failures, or repeated dead ends, also run:

```bash
./pmem rationale context --task "<current task>" --out .project-memory/reports/RATIONALE_CONTEXT.md
```

Read `.project-memory/reports/RATIONALE_CONTEXT.md` before repeating an approach. Rationale stores verified decisions, rejected alternatives, and evidence; never use it to store hidden chain-of-thought.

After editing, run:

```bash
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem tests --base HEAD --explain
```

Run the targeted test commands returned by `./pmem tests --base HEAD`.

If retrieved memory looks incomplete or surprising, run:

```bash
./pmem search --query "<task terms>" --debug
```

For memory quality checks, run:

```bash
./pmem stale
./pmem audit
./pmem audit --secrets
./pmem eval --file .project-memory/evals/search.jsonl
```

Use project-local tooling and sandboxes for verification whenever possible. Inspect command output locally and summarize the relevant result; do not send long raw outputs unless they are necessary to diagnose an ambiguous failure.

When a durable research finding, architecture note, SEO rule, design principle, UX rule, product mechanic, or content rule changes, update project knowledge:

```bash
./pmem knowledge add --type "<research|architecture|seo|design|ux|product|decision>" --title "<title>" --file "<markdown file>"
./pmem knowledge update --id "<knowledge id>" --file "<markdown file>"
```

Use `knowledge update` for changed principles. Use `knowledge retire` for obsolete entries. Do not keep two competing `current` records for the same rule.

When a durable decision, rejected approach, experiment result, invariant, or cause changes, update project rationale:

```bash
./pmem rationale add --type "<decision|rejection|experiment|constraint>" --title "<title>" --file "<markdown file>"
./pmem rationale update --id "<rationale id>" --file "<markdown file>"
```

Use `rationale update` for changed causes. Use `rationale retire` for obsolete explanations. Do not keep two competing `current` rationales for the same decision.

If a test fails:

```bash
mkdir -p .project-memory/logs
./pmem record-failure --command "<failed command>" --log-file "<log path>"
./pmem context --task "fix failing tests after current change" --base HEAD --out .project-memory/reports/CHANGE_CONTEXT.md
```

Final responses after code changes must include files changed, symbols changed, impact checked, tests run, knowledge/rationale updates if any, failure memory updates, and remaining risk.

External skills may also exist in `.agents/skills/`. Use them when relevant, but they do not replace this mandatory project-memory protocol.

Additional project rules may exist in `.agents/rules/`.

Never index, print, or store secrets.
