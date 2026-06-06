## Local Project Memory Protocol

This repository uses local Dependency Graph RAG project memory.

The memory system is installed in:

```text
.project-memory/
tools/project_memory/
.agents/skills/dependency-graph-rag/
```

Before any meaningful code, config, schema, dependency, API, test, build, routing, migration, auth, persistence, or architecture change, run:

```bash
./pmem doctor
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "<current task>" --base HEAD --out .project-memory/reports/CHANGE_CONTEXT.md
```

Read `.project-memory/reports/CHANGE_CONTEXT.md` before editing. Identify target files, target symbols, direct dependencies, reverse dependencies, affected tests, related previous failures, architecture constraints, and low-confidence graph areas.

Keep context bounded. Prefer local `pmem` reports, targeted searches, local tests, and concise summaries over pasting large files or logs into the chat. Open full files, full knowledge notes, or long logs only when the short local reports are insufficient.

For research, product, UX, design, SEO, architecture, content, positioning, or other principle-heavy work, also run:

```bash
./pmem knowledge context --task "<current task>" --out .project-memory/reports/KNOWLEDGE_CONTEXT.md
```

Read `.project-memory/reports/KNOWLEDGE_CONTEXT.md` and open the referenced full Markdown files before relying on a research note or project principle.

After editing, run:

```bash
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem tests --base HEAD
```

Run the targeted test commands returned by `./pmem tests`.

Use project-local tooling and sandboxes for verification whenever possible. Summarize command results; do not send long raw outputs unless they are necessary to diagnose an ambiguous failure.

When a durable research finding, architecture note, SEO rule, design principle, UX rule, product mechanic, or content rule changes, update project knowledge:

```bash
./pmem knowledge add --type "<research|architecture|seo|design|ux|product|decision>" --title "<title>" --file "<markdown file>"
./pmem knowledge update --id "<knowledge id>" --file "<markdown file>"
```

Use `knowledge update` for changed principles. Use `knowledge retire` for obsolete entries. Do not keep two competing `current` records for the same rule.

If a test fails:

```bash
mkdir -p .project-memory/logs
./pmem record-failure --command "<failed command>" --log-file "<log path>"
./pmem context --task "fix failing tests after current change" --base HEAD --out .project-memory/reports/CHANGE_CONTEXT.md
```

Final responses after code changes must include files changed, symbols changed, impact checked, tests run, knowledge updates if any, failure memory updates, and remaining risk.

External skills may also exist in `.agents/skills/`. Use them when relevant, but they do not replace this mandatory project-memory protocol.

Never index, print, or store secrets.
