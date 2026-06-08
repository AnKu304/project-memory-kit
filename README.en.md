# project-memory-kit

Russian version: [README.md](README.md)

Version changes: [CHANGELOG.md](CHANGELOG.md)

`project-memory-kit` adds local project memory for coding agents. It keeps project context next to the code: files, symbols, imports, reverse dependencies, relevant tests, previous failures, research, and rationale.

The goal is simple: several chats can work on one project without losing dependency context.

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

Before editing:

```bash
./pmem doctor
./pmem tasks check
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "<task>" --base HEAD --reset-task --out .project-memory/reports/CHANGE_CONTEXT.md
```

Context stays bounded: short snippets, ids, and paths to full records. Large files, logs, and reports are inspected with local commands first; only the relevant result or short excerpt goes into the model context.

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
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "task description"
./pmem search --query "payment validation" --limit 10
./pmem search --query "payment validation" --limit 10 --debug
./pmem tests --base HEAD
./pmem audit
./pmem audit --secrets
./pmem optimize
./pmem watch --serve --interval 5
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

## MCP

`./pmem mcp` starts a local stdio MCP server over the same runtime and the same `.project-memory/` database. It does not create separate memory or send data to an external service.

MCP Task Write Tools can create, assign, and close tasks under `.agents/tasks/`: `pmem_tasks_create`, `pmem_tasks_assign`, and `pmem_tasks_close`. Written tasks are re-indexed locally.

## Version Updates

Short version:

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
