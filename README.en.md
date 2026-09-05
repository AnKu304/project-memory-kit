# project-memory-kit

Russian version: [README.md](README.md)

Version changes: [CHANGELOG.md](CHANGELOG.md)

`project-memory-kit` adds local project memory for coding agents. It keeps project context next to the code: files, symbols, imports, reverse dependencies, relevant tests, previous failures, research, and rationale.

The goal is simple: several chats can work on one project without losing dependency context.

## Local project memory

PMEM serves agents with bounded context, search, dependencies, knowledge and
decision rationale. Code is not the only source: marketing, design, research
and analytics may live in the same isolated project.

- L1: current task state and working context.
- L2: project sources, durable knowledge and decision evidence.
- L3: explicitly assigned shared rules/skills, not a merged private-project database.

These are logical levels, not three copies. Project scope, memory purpose,
subject domain and audience (`project`/`agent_tooling`) are independent.
Default search excludes agent tooling; `--audience all` includes it only within
the same root. It grants no access to other projects.

Causal and other relations retain source SHA-256 and lifecycle. They remain
assertions, not automatically proven causes.
[Layer and relation contract](docs/memory-layers-and-relations.md).

## Non-Git project container

For an explicitly selected project folder containing separate code repositories:

```bash
pmem init --target "/path/Working projects/Project name" --no-git-init --agent multiagent
```

Upgrade preserves this mode and never initializes Git in the container. Do not
select the parent Working projects folder or Desktop. Code and allowed text
materials inside the chosen root are eligible; `agent/`, archives, sensitive
paths, databases, runtime and symlink sources are excluded. Marketing need not
be copied into Git. Run `./pmem index --mode full` separately after checking scope.
Installation starts no watcher and does not index neighbouring projects by default.

Git diff/impact and Git-based test selection are **unavailable** at a non-Git
container root. Nested repositories are indexed as sources, but cross-repository
Git diff is not implemented. Use the relevant repository and its tools for exact
Git impact; empty change lists are not evidence of safety.

## MCP reads and writes

The installed `./pmem mcp-config --root "/exact/root" --format json` emits configuration.
One MCP serves one root. A configuration file does not prove the client has
loaded the server: verify `tools/list` and actual operations.

`pmem_overview` returns a bounded index map without models/scanning;
`pmem_relations` returns assertions and source status. CLI equivalents:

```bash
./pmem overview --limit 20
./pmem relations --kind knowledge --id decision-id --limit 20
```

`pmem_knowledge_add/update` and `pmem_rationale_add/update` use the existing
write lock/queue. `file` must already exist relative to this root. `links` accepts
legacy strings/structured assertions; omitted update links preserve the batch,
`[]` clears it. CLI supports `--links-json` and legacy `--link`.
`queued`, `completed=false`, `record=null` means pending, not persisted.
Verify returned ID/version with show and focused search after a saved write.

Local Qdrant/FastEmbed is optional. Busy-vector search returns available
lexical/graph results with explicit degradation, not a semantic-success claim.
Context reuses embeddings only within one request, without a resident server.
Full database restore from Markdown and cross-project shared retrieval are not
implemented. Tencent's web UI is not required.

## What It Installs

Profiles:

- `Codex`: `AGENTS.md`, `.agents/skills/`, `.project-memory/`, `tools/project_memory/`, `pmem`.
- `Claude`: `CLAUDE.md`, `.claude/rules/`, `.claude/skills/`, `.claude/commands/`.
- `Multi-agent`: shared roles, rules, and tasks for multiple agents, plus Codex and Claude instructions.

If `AGENTS.md` or `CLAUDE.md` already exists, the installer preserves user content and updates only the managed block:

```text
<!-- PMEM:BEGIN -->
...
<!-- PMEM:END -->
```

External skills are not managed by this project. Install them separately and document when to use them in `AGENTS.md` or `CLAUDE.md`.

## Install

From the target repository root:

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target .
```

npm/npx option:

```bash
npx --yes --package github:AnKu304/project-memory-kit pmem init --target .
```

Interactive install:

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target . --interactive
```

The wizard asks for the agent profile, task templates, Human layer, vector backend, and MCP config. Commands without `--interactive` work as before.

Choose a profile:

```bash
pmem init --target . --agent codex
pmem init --target . --agent claude
pmem init --target . --agent multiagent
```

Check the install:

```bash
./pmem doctor
./pmem index --mode full
```

## Upgrade

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem upgrade --target . --agent auto
```

Upgrade refreshes managed files and runs migrations. Databases, logs, and runtime state under `.project-memory/` are preserved.

You can add a profile during upgrade:

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem upgrade --target . --agent claude
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem upgrade --target . --agent multiagent
```

## Agent Workflow

Start a meaningful task with one MCP `pmem_context` call or CLI context:

```bash
./pmem context --task "<task>" --base HEAD --reset-task --out .project-memory/reports/CHANGE_CONTEXT.md
```

Run doctor on setup, runtime/configuration changes, or malfunction, not every task. If `.agents/tasks/` exists, inspect `./pmem tasks check`. For a complex task, choose `--compiled` instead of ordinary context; do not automatically run both.

Context already includes impact, search, knowledge/rationale, failures, and test recommendations. Open relevant sources and records by ID; fetch full text only when excerpts are insufficient.

Run `./pmem index --mode changed` for stale/missing sources or after indexed files change before handoff, unless auto-index already verified the same inputs. Use `./pmem status` when uncertain. Changed mode may inspect the entire allowed root; it is not a path-only API. Initial full indexing requires an explicitly selected project.

After changes, refresh impact and test selection when needed:

```bash
./pmem impact --base HEAD --format markdown
./pmem tests --base HEAD
```

When a test fails:

```bash
mkdir -p .project-memory/logs
./pmem record-failure --command "<failed command>" --log-file "<log path>"
```

## Multi-chat Work

Several chats can read memory in parallel. Write commands are serialized through a short local lock so SQLite/Qdrant state is not corrupted:

- reads: `status`, `search`, `context`, `impact`, `tests`, `knowledge context`, `rationale context`;
- writes: `index`, `knowledge add/update/retire`, `rationale add/update/retire`, `record-failure`, `human export/sync/graph`, `tasks close/import`, `modules set`.

If another chat is writing, the command waits for `concurrency.write_lock.timeout_seconds`. If the lock is still busy, the command is stored in the local queue:

```bash
./pmem lock status
./pmem lock clear
./pmem queue list
./pmem queue drain
```

`lock clear` removes stale locks only. Use `lock clear --force` only when you are sure the writer process has stopped.

`watch --serve` does not hold the global write lock between checks. If auto-index sees an active writer from another chat, it skips the current pass quickly and uses the existing index.

Indexing and audit use a pruned project walker: ignored directories such as `node_modules/`, `.project-memory/`, `.playwright-cli/`, `.playwright-mcp/`, `.turbo/`, and `coverage/` are skipped before descent.

The binary-content probe reads only the first 2 KB instead of loading the whole
file into memory. Freshness checks read one indexed-hash snapshot instead of
opening a SQLite connection per file; source contents are still hashed, with
no TTL cache that could hide changes. These optimize specific operations,
not guarantee a fixed RAM footprint for the entire system.

## Core Commands

Installer:

```bash
pmem init --target .
pmem init --target . --interactive
pmem install --target .
pmem upgrade --target . --agent auto
pmem upgrade --target . --with-vector
pmem uninstall --target . --keep-memory
pmem version
```

Installed runtime:

```bash
./pmem doctor
./pmem status
./pmem report
./pmem impact --base HEAD --format markdown
./pmem context --task "task description"
./pmem context --task "task description" --compiled
./pmem search --query "payment validation" --limit 10
./pmem search --query "payment validation" --limit 10 --debug
./pmem tests --base HEAD
./pmem audit
./pmem audit --secrets
./pmem optimize
./pmem watch --serve --interval 5
./pmem lock status
./pmem queue list
./pmem queue drain
```

Tasks:

```bash
./pmem tasks check
./pmem tasks list
./pmem tasks close --file .agents/tasks/example.md --summary "Done"
./pmem tasks linear status
./pmem tasks linear export --out .project-memory/linear/tasks-export.json
./pmem tasks linear import --file .project-memory/linear/issues.json
```

Memory layers:

```bash
./pmem knowledge add --type research --title "Resource mechanics" --file notes/research.md
./pmem knowledge update --id resource-mechanics --file notes/research.md
./pmem knowledge context --task "redesign product page"
./pmem rationale add --type decision --title "Use SQLite" --file notes/rationale/sqlite.md
./pmem rationale context --task "change memory database"
./pmem human export
./pmem human sync
./pmem human graph --html
```

MCP:

```bash
./pmem mcp --root .
./pmem mcp-config --root .
./pmem mcp-config --root . --client claude --write
```

## Memory Layers

Knowledge Layer

Stores research, architecture, SEO, design, UX, product principles, and other durable project knowledge. Full records live in `.project-memory/knowledge/**/*.md`; context usually receives short snippets and a path to the full version.

Rationale Layer

Stores decision causes: chosen approaches, rejected alternatives, errors, experiments, and invariants. Each record should point to verifiable evidence: a test, log, diff, file, failure, or commit.

Human Layer

Optional Obsidian-like layer. It exports current `knowledge` and `rationale` records into Markdown with frontmatter, backlinks, and a graph. It is disabled by default:

```bash
./pmem modules set human --enabled true
./pmem human export
./pmem human graph --html
```

Hybrid Search

Search combines SQLite FTS5 `bm25()`, vector score, term coverage, path, graph proximity, confidence, layer, and recency. `./pmem search --debug` shows ranking components.

Vector Backend

The default is `backend: auto`: Qdrant/FastEmbed are used when available; otherwise deterministic fallback is used. For a managed runtime:

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem upgrade --target . --with-vector
./pmem doctor
```

For multiple chats, you can point the project at a local Qdrant server in `.project-memory/config.yaml`:

```yaml
vector:
  backend: qdrant
  url: http://127.0.0.1:6333
```

When `url` is not set, embedded local Qdrant or fallback mode is preserved. Embedded Qdrant is guarded by a short local lock: if another process is using it, `backend: auto` quickly uses the SQLite/BM25 path without a long wait.

Context Compiler

`./pmem context --compiled` builds a task packet with local evidence, preflight/postflight gates, impact, ranked search, knowledge/rationale, lifecycle, and provenance. Use it for complex tasks where context should stay bounded and evidence-backed.

## MCP

`./pmem mcp` starts a local stdio MCP server over the same runtime and the same `.project-memory/` database. It does not create separate memory or send data to an external service.

MCP Task Write Tools can create, assign, and close tasks under `.agents/tasks/`: `pmem_tasks_create`, `pmem_tasks_assign`, and `pmem_tasks_close`. Written tasks are re-indexed locally.

## Version Updates

Short version:

- `0.23.0`: isolated containers, sourced relations, MCP writes and resource optimizations.
- `0.22.2`: Pruned Traversal Fix; status/index/context/audit skip ignored heavy directories before descent.
- `0.22.1`: Contention Fix; `watch --serve` no longer holds write-lock, auto-index skips when busy, embedded Qdrant is guarded with fast fallback.
- `0.22.0`: Multi-chat Write Concurrency; SQLite timeout, managed write lock, stale lock cleanup, write queue, Qdrant server URL.
- `0.21.0`: Depth Improvements; compiled context, retrieval diversity, golden evals, test graph bindings, lifecycle, local evidence, task gates, provenance.
- `0.20.0`: CI Runtime Warning Cleanup; GitHub Actions moved to Node 24-capable actions and a Node 22/24 matrix.
- `0.19.0`: MCP Task Write Tools; MCP can create, assign, and close `.agents/tasks/`.
- `0.18.0`: Install Wizard; `pmem init --interactive` for choosing the profile and optional modules.
- `0.17.0`: Human Graph Viewer; static `human graph --html` for viewing the Human graph.
- `0.16.0`: Memory Quality Dashboard; `pmem report` for local Markdown/JSON memory health reports.
- `0.15.0`: TS/Next Graph Depth; route-to-component edges, client/server boundary, and API route methods.
- `0.14.0`: Real File Watcher; local hash-based polling watcher with explicit `watch --serve`.
- `0.13.0`: Linear Sync; local export/import bridge for Linear tasks without mandatory dependencies.
- `0.12.0`: Bidirectional Human Sync; two-way Human layer sync with conflict detection.

Full list: [CHANGELOG.md](CHANGELOG.md)

## Development

Run this repository's checks:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:src/project_memory_kit/installer/runtime python3 -m unittest discover -s tests
npm run check
```
