# project-memory-kit

Russian version: [README.md](README.md)

Version changes: [CHANGELOG.md](CHANGELOG.md)

`project-memory-kit` adds local project memory for coding agents.

The memory lives inside the repository, so several chats can work on the same project without losing context. Agents can inspect files, symbols, imports, reverse dependencies, relevant tests, previous failures, and durable project principles before editing.

## What It Installs

Install profiles:

- `Codex` by default: `AGENTS.md` and `.agents/skills/`.
- `Claude` optional: `CLAUDE.md`, `.claude/rules/`, `.claude/skills/`, `.claude/commands/`.
- `Multi-agent` optional: a universal structure for multiple agents, plus Codex and Claude instructions.

Base Codex profile:

```text
AGENTS.md
.agents/skills/dependency-graph-rag/
.project-memory/config.yaml
.project-memory/.gitignore
.project-memory/README.md
.project-memory/install.json
.project-memory/knowledge/
.project-memory/rationale/
.project-memory/evals/
tools/project_memory/
pmem
pmem.ps1
.gitignore
```

Claude profile adds:

```text
CLAUDE.md
.claude/settings.json
.claude/rules/project-memory.md
.claude/skills/dependency-graph-rag/
.claude/commands/pmem-context.md
.claude/commands/pmem-status.md
.claude/commands/pmem-audit.md
```

Multi-agent adds both instruction sets and role files:

```text
.agents/rules/
.agents/roles/
.agents/tasks/
.claude/agents/
```

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
pipx run --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target .
```

npm/npx option:

```bash
npx --yes --package github:AnKu304/project-memory-kit pmem init --target .
```

Choose a profile with `--agent`:

```bash
# Codex by default
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target .

# Claude
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target . --agent claude

# Multi-agent
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target . --agent multiagent
```

To force a fresh GitHub commit:

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target .
```

With a managed vector runtime:

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target . --with-vector
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

Upgrade refreshes managed files and runs migrations. Databases and runtime state under `.project-memory/` are preserved.

You can add a profile during upgrade:

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem upgrade --target . --agent claude
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem upgrade --target . --agent multiagent
```

## Agent Workflow

Before editing:

```bash
./pmem doctor
./pmem tasks check
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "<task>" --base HEAD --reset-task --out .project-memory/reports/CHANGE_CONTEXT.md
```

Context stays bounded: short snippets, ids, and paths to full records. Agents should inspect large files, logs, and reports with local tools first, then bring only relevant findings and short excerpts into the working context. Full text is opened only when the local summary is insufficient.

After editing:

```bash
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem tests --base HEAD
```

When a test fails:

```bash
mkdir -p .project-memory/logs
./pmem record-failure --command "<failed command>" --log-file "<log path>"
```

## Commands

Installer:

```bash
pmem init --target .
pmem init --target . --agent claude
pmem init --target . --agent multiagent
pmem install --target .
pmem upgrade --target . --agent auto
pmem upgrade --target . --with-vector
pmem uninstall --target . --keep-memory
pmem uninstall --target . --purge
pmem version
```

Installed runtime:

```bash
./pmem version
./pmem doctor
./pmem status
./pmem stale
./pmem migrate
./pmem modules list
./pmem modules set human --enabled true
./pmem modules set human --enabled false
./pmem index --mode full
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "task description"
./pmem audit
./pmem audit --secrets
./pmem optimize
./pmem eval --file .project-memory/evals/search.jsonl
./pmem tasks check
./pmem tasks list
./pmem tasks close --file .agents/tasks/example.md --summary "Done"
./pmem tasks linear status
./pmem tasks linear export --out .project-memory/linear/tasks-export.json
./pmem tasks linear import --file .project-memory/linear/issues.json
./pmem human status
./pmem human export
./pmem human sync
./pmem human search --query "design rules"
./pmem human graph
./pmem knowledge add --type research --title "Resource mechanics" --file notes/research.md
./pmem knowledge update --id resource-mechanics --file notes/research.md
./pmem knowledge search --query "SEO rules"
./pmem knowledge conflicts
./pmem knowledge context --task "redesign product page"
./pmem knowledge show --id resource-mechanics
./pmem knowledge retire --id old-design-rules
./pmem rationale add --type decision --title "Use SQLite" --file notes/rationale/sqlite.md
./pmem rationale update --id use-sqlite --file notes/rationale/sqlite.md
./pmem rationale search --query "why not postgres"
./pmem rationale conflicts
./pmem rationale context --task "change memory database"
./pmem rationale show --id use-sqlite
./pmem rationale retire --id old-storage-choice
./pmem tests --base HEAD
./pmem tests --base HEAD --explain
./pmem search --query "payment validation" --limit 10
./pmem search --query "payment validation" --limit 10 --debug
./pmem search --query "pricing SEO" --layer knowledge
./pmem search --query "why sqlite" --layer rationale
./pmem search --query "design principles" --layer human
./pmem watch
./pmem watch --once
./pmem watch --interval 5 --max-runs 1
./pmem watch --serve --interval 5
./pmem record-failure --command "npm test" --log-file ".project-memory/logs/test.log"
./pmem mcp --root .
./pmem mcp-config --root .
./pmem mcp-config --root . --client claude --write
./pmem tasks linear status
./pmem tasks linear export --out .project-memory/linear/tasks-export.json
./pmem tasks linear import --file .project-memory/linear/issues.json
```

## Local MCP

`./pmem mcp` starts a local stdio MCP server over the same runtime and the same `.project-memory/` database. It does not create separate memory and does not send data to an external service.

Example MCP client config:

```toml
[mcp_servers.project_memory]
command = "/absolute/path/to/repo/pmem"
args = ["mcp", "--root", "/absolute/path/to/repo"]
```

Print this snippet with:

```bash
./pmem mcp-config --root .
./pmem mcp-config --root . --client claude --write
```

Available MCP tools:

```text
pmem_doctor
pmem_index
pmem_status
pmem_context
pmem_impact
pmem_tests
pmem_search
pmem_search_debug
pmem_eval
pmem_audit
pmem_modules
pmem_watch_status
pmem_tasks
pmem_human_status
pmem_human_export
pmem_human_search
pmem_human_graph
pmem_knowledge_context
pmem_knowledge_search
pmem_knowledge_show
pmem_rationale_context
pmem_rationale_search
pmem_rationale_show
pmem_record_failure
```

MCP is useful for short structured tool responses to agents. The CLI commands remain the baseline verification path and fallback when an MCP client is not configured.

## How It Works

- SQLite stores the project graph: files, symbols, chunks, imports, calls, inheritance, failures.
- The knowledge layer stores research, architecture, SEO, design, UX, product mechanics, and other project principles.
- Full knowledge records live in `.project-memory/knowledge/**/*.md`; SQLite stores metadata, status, versions, and links.
- Knowledge search uses only `current` records by default. When a principle changes, `knowledge update` keeps one current record instead of creating a competing copy.
- The rationale layer stores verified causes: decisions, rejected alternatives, experiments, invariants, and evidence.
- Full rationale records live in `.project-memory/rationale/**/*.md`; context receives only short snippets, ids, score/reason, and paths to full records.
- Hybrid search combines SQLite FTS5 `bm25()`, vector score, term coverage, path matches, graph proximity, confidence, layer, and recency.
- `./pmem search --debug` shows ranking components.
- `search`, `context`, `impact`, and `tests` automatically run a local `changed` index when the database is empty or stale.
- `status`, `stale`, `audit`, `eval`, `tests --explain`, and `watch` help check memory quality locally.
- `audit --secrets` scans project files for possible secrets without printing the matched values.
- `optimize` runs local SQLite maintenance.
- Full records are opened only when needed.
- Edges have `confidence`; more exact bindings receive higher scores.
- Qdrant local + FastEmbed provide semantic search when available.
- If Qdrant/FastEmbed are not available, deterministic fallback keeps install and indexing usable.
- The Python parser extracts modules, classes, functions, methods, imports, calls, inheritance, and docstrings.
- The JS/TS parser extracts modules, classes, functions, methods, imports, exports, require, dynamic imports, calls, and JSX component references.
- The JS/TS parser understands `tsconfig` aliases, workspace/package aliases, and Next.js app routes.
- The Next.js graph adds route-to-component edges, `use client`/server boundary metadata, and HTTP methods for `route.ts/js`.
- JS/TS uses a configurable backend. The default is `auto`: TypeScript compiler API when `node` and `typescript` are available in the project, otherwise the built-in lexical parser. `tree_sitter` and `lsp` are reserved optional backends without mandatory dependencies.
- A local MCP server exposes doctor/status/index/context/impact/search/search_debug/tests/eval/audit/modules/tasks/knowledge/rationale tools over the same `pmem` runtime.
- `tasks check` shows open handoff/user tasks from `.agents/tasks/`, so agents do not miss work left by another chat.
- `tasks close` closes a task file, appends a completion block, and re-indexes the changed task.
- `tasks linear` is a local Linear bridge: it exports `.agents/tasks/` to JSON and imports issues back into task files.
- The `human` module creates an Obsidian-like Markdown layer over current knowledge/rationale: `.project-memory/human/index.md`, generated notes, `graph.mmd`, and `graph.json`.
- `search --layer human` searches generated human notes.
- `mcp-config --client claude --write` can write `.mcp.json` while preserving existing settings.
- Secrets, `.env` files, dependency directories, build outputs, caches, and binary files are not indexed.

## Optional Modules

Modules are configured in `.project-memory/config.yaml`.

```yaml
modules:
  human:
    enabled: false
```

`human` is disabled by default. Enabling it creates `.project-memory/human/`; disabling it does not delete data.

The Human layer is for a human-readable Obsidian-like view over project memory. It does not replace `knowledge` or `rationale`; it exports their current records into Markdown with frontmatter, backlinks, and a visual graph:

```bash
./pmem modules list
./pmem modules set human --enabled true
./pmem modules set human --enabled false
./pmem human export
./pmem human sync
./pmem human graph
./pmem human search --query "SEO rules"
```

`human sync` pulls manual edits from generated Human notes back into `knowledge` or `rationale`. If both the Human note and the source record changed after the last export, the command reports a conflict instead of overwriting data silently.

## Linear Sync

Task synchronization with Linear

The Linear bridge is disabled by default and does not require the Linear SDK. `.agents/tasks/` remains the local task source, while `.project-memory/linear/*.json` acts as an exchange file for the Linear plugin, MCP, or manual sync.

```bash
./pmem tasks linear status
./pmem tasks linear export --out .project-memory/linear/tasks-export.json
./pmem tasks linear import --file .project-memory/linear/issues.json
```

Import creates or updates Markdown tasks in `.agents/tasks/linear/` and re-indexes them so other chats see the tasks through `./pmem tasks check`.

## Memory Evals

Local evals live in `.project-memory/evals/*.jsonl`.

Example line:

```json
{"query":"payment validation","expect_path":"src/payments.py"}
```

Run:

```bash
./pmem eval --file .project-memory/evals/search.jsonl
```

## Version Updates

Short version:

- `0.15.0`: TS/Next Graph Depth; route-to-component edges, client/server boundary, and API route methods.
- `0.14.0`: Real File Watcher; local hash-based polling watcher with explicit `watch --serve`.
- `0.13.0`: Linear Sync; local export/import bridge for Linear tasks without mandatory dependencies.
- `0.12.0`: Bidirectional Human Sync; two-way Human layer sync with conflict detection.
- `0.11.0`: Human/Obsidian-like layer, `human export/sync/search/graph`, `search --layer human`, MCP human tools, `tasks close`.
- `0.10.0`: npm package smoke, tarball validation, `prepack`, strict package `files`, Python 3.11+ check in the Node wrapper, npm distribution guide.
- `0.9.0`: safe profile upgrades, workspace/package aliases for JS/TS, Next.js route metadata, `.agents/tasks/`, `pmem tasks`, Claude `.mcp.json` writer, secret allowlist/entropy/JWT scan, eval templates, quality guards.
- `0.8.0`: npm/npx distribution, `Codex`/`Claude`/`Multi-agent` profiles, Claude Code structure, CI, `audit --secrets`, `optimize`, `mcp-config`.
- `0.7.0`: hybrid search, `search --debug`, `status`, `stale`, `eval`, `audit`, `tests --explain`, `watch --once`, new MCP tools, parser backend config.
- `0.6.0`: BM25, auto-index, deleted-file cleanup, optional `human` module.
- `0.5.0`: local MCP server.

Full list: [CHANGELOG.md](CHANGELOG.md)

## Knowledge Layer

Types are flexible. Good defaults are `research`, `architecture`, `seo`, `design`, `ux`, `product`, `decision`, `policy`, and `note`.

Example:

```bash
./pmem knowledge add --type seo --title "Product Page SEO" --file docs/seo/product-page.md --tags seo,content
./pmem knowledge context --task "update product page copy"
```

`knowledge context` returns a short list of current records and paths to full Markdown. Open the full record only when it is needed for the task.

When a rule changes:

```bash
./pmem knowledge update --id product-page-seo --file docs/seo/product-page.md
```

When it is obsolete:

```bash
./pmem knowledge retire --id old-product-page-seo
```

## Rationale Layer

The rationale layer helps avoid repeating dead ends. It records chosen decisions, rejected approaches, error causes, experiments, and project invariants. Each record should point to facts: a test, log, diff, file, failure, or commit.

Example:

```bash
./pmem rationale add --type decision --title "Use SQLite as Source of Truth" --file docs/rationale/sqlite.md --why "local-first and upgrade-safe" --rejected "Postgres: unnecessary server dependency" --evidence "tests: upgrade preserves graph.sqlite"
./pmem rationale context --task "replace local database"
```

When a cause changes:

```bash
./pmem rationale update --id use-sqlite-as-source-of-truth --file docs/rationale/sqlite.md
```

When it is obsolete:

```bash
./pmem rationale retire --id old-storage-rationale
```

## Vector Backend

Configuration lives in `.project-memory/config.yaml`:

```yaml
vector:
  backend: auto
  collection: project_memory_chunks
  embedding_model: null
```

Modes:

- `auto`: use Qdrant/FastEmbed when available; otherwise fallback.
- `qdrant`: require Qdrant/FastEmbed and fail if unavailable.
- `fallback`: do not use Qdrant/FastEmbed.

For semantic search, install dependencies into the Python used by `./pmem`:

```bash
python3 -m pip install qdrant-client fastembed
./pmem doctor
./pmem index --mode full
```

Or install the managed runtime:

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem upgrade --target . --with-vector
./pmem doctor
```

To use a specific Python:

```bash
PYTHON=/path/to/python ./pmem doctor
PYTHON=/path/to/python ./pmem index --mode full
```

## Development

Run the test suite:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:src/project_memory_kit/installer/runtime python3 -m unittest discover -s tests
```
