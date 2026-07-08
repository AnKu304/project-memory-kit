## Local Project Memory Protocol

This repository uses local Dependency Graph RAG project memory.

Claude-specific project memory rules are imported here:

@.claude/rules/project-memory.md

The memory system is installed in:

```text
.project-memory/
tools/project_memory/
.claude/skills/dependency-graph-rag/
```

If the local MCP server is configured, use the equivalent `pmem_*` tools for bounded context, search, impact, tests, knowledge, and rationale. CLI commands remain the fallback and verification baseline.

Before meaningful edits, run:

```bash
./pmem doctor
./pmem status
./pmem impact --base HEAD --format markdown
./pmem context --task "<current task>" --base HEAD --reset-task --out .project-memory/reports/CHANGE_CONTEXT.md
```

Read `.project-memory/reports/CHANGE_CONTEXT.md` before editing. Keep context bounded: inspect large files, logs, and reports locally, then bring only relevant findings, short excerpts, ids, and paths into the working context.

Run `./pmem index --mode changed` before editing only when `./pmem status` reports stale or missing files in the task area, retrieved context looks incomplete, or the task changes shared architecture, routes, API contracts, schemas, dependencies, or tests. Always run it after meaningful edits before final verification.

If `.agents/tasks/` exists, check active user tasks and handoffs before starting:

```bash
./pmem tasks check
```

When a task file has been completed, close it instead of leaving it active:

```bash
./pmem tasks close --file "<task md path>" --summary "<what changed>"
```

For research, architecture, SEO, design, UX, product, content, or principle-heavy work, also run:

```bash
./pmem knowledge context --task "<current task>" --out .project-memory/reports/KNOWLEDGE_CONTEXT.md
```

For "why", rejected approaches, prior failures, storage/tool choices, and repeated dead ends, also run:

```bash
./pmem rationale context --task "<current task>" --out .project-memory/reports/RATIONALE_CONTEXT.md
```

After editing, run:

```bash
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem tests --base HEAD --explain
```

Use `./pmem search --query "<task terms>" --debug` when retrieved memory looks incomplete. Use `./pmem audit --secrets` before commits that touched config, auth, env handling, integrations, or credentials.

Multiple chats may read project memory at the same time. Write commands are serialized by a local write lock. If a write command reports `queued write`, do not assume the memory update has been applied; tell the user and run or ask for:

```bash
./pmem lock status
./pmem queue list
./pmem queue drain
```

Use `./pmem lock clear` only for stale locks. Use `./pmem lock clear --force` only when the writer process is known to be stopped.

`./pmem watch --serve` is allowed as a background freshness helper, but it must not be treated as a reason to wait on memory. Auto-index may skip a pass when another writer is active; continue with the current index and run `./pmem index --mode changed` after the writer finishes.

Embedded local Qdrant is guarded by `qdrant.lock`. If vector access is busy, prefer the SQLite/BM25 results already returned by `pmem search/context` instead of retrying in a loop. For heavy parallel chat work, configure a local Qdrant server through `vector.url`.

Project-wide memory scans must use the pruned walker in `tools.project_memory.ignore`. Do not reintroduce root-wide `Path.rglob("*")` in status, index, context, tests, or audit paths.

If the optional human layer is enabled, refresh it after durable knowledge or rationale changes:

```bash
./pmem human export
./pmem human graph
```

Never index, print, or store secrets.
