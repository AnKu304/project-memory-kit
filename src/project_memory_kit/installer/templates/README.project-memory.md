# Project Memory

This directory stores local Dependency Graph RAG state.

Project knowledge lives in `knowledge/`. These Markdown files are the full source for research notes, architecture decisions, SEO rules, design principles, UX rules, product mechanics, and other durable project context.

Project rationale lives in `rationale/`. These Markdown files are the full source for verified decisions, rejected alternatives, experiments, invariants, and evidence-backed "why" records.

Memory evals live in `evals/`. These JSONL files test whether local search returns expected project files or records.

Local MCP is available through:

```bash
./pmem mcp --root .
```

Use it only with a local MCP client. It reads the same `.project-memory/` state and does not create a separate database.

Vector state is controlled by `config.yaml`:

- `vector.backend: auto` tries Qdrant local + FastEmbed and falls back offline.
- `vector.backend: qdrant` requires Qdrant/FastEmbed and fails loudly if unavailable.
- `vector.backend: fallback` keeps deterministic bootstrap records only.

Hybrid search uses SQLite FTS5 `bm25()`, vector score when available, term coverage, path matches, graph proximity, confidence, layer, and recency. `search`, `context`, `impact`, `tests`, and `watch --once` run a local `changed` index automatically when indexed files are missing or stale.

Useful checks:

```bash
./pmem status
./pmem stale
./pmem search --query "<query>" --debug
./pmem eval --file .project-memory/evals/search.jsonl
./pmem audit
./pmem audit --secrets
./pmem optimize
./pmem report
./pmem tasks check
./pmem tasks linear status
./pmem human status
./pmem tests --base HEAD --explain
./pmem lock status
./pmem queue list
./pmem watch
./pmem watch --once
./pmem watch --serve --interval 5
```

Multiple chats may read memory at the same time. Write commands use a short local lock. If a write command reports `queued write`, run:

```bash
./pmem queue drain
```

Use `./pmem lock clear` only for stale locks.

`watch --serve` does not keep the write lock while it sleeps. If auto-index sees another active writer, it skips that pass and uses the current index.

Embedded local Qdrant uses `.project-memory/runtime/qdrant.lock`. In `backend: auto`, busy vector access falls back to SQLite/BM25 instead of blocking for a long time.

Project-wide memory scans use a pruned walker. Ignored generated directories such as `node_modules/`, `.project-memory/`, `.playwright-cli/`, `.playwright-mcp/`, `.turbo/`, and `coverage/` are skipped before descent.

Optional modules are controlled in `config.yaml`:

```yaml
modules:
  human:
    enabled: false
```

`human` is disabled by default. Enabling it creates `human/`; disabling it keeps existing files.

When enabled, Human export creates an Obsidian-like Markdown view over current knowledge and rationale:

```bash
./pmem modules set human --enabled true
./pmem human export
./pmem human sync
./pmem human graph
./pmem human graph --html
./pmem human search --query "<query>"
```

Generated files include `human/index.md`, `human/knowledge/**/*.md`, `human/rationale/**/*.md`, `human/graph.mmd`, `human/graph.json`, and optional `human/graph.html`.
`human sync` can pull manual edits from generated Human notes back into source memory records, and it reports conflicts when both sides changed.

For multi-chat vector writes, optional Qdrant server mode can be configured:

```yaml
vector:
  backend: qdrant
  url: http://127.0.0.1:6333
```

Linear bridge is available without extra runtime dependencies:

```bash
./pmem tasks linear status
./pmem tasks linear export --out .project-memory/linear/tasks-export.json
./pmem tasks linear import --file .project-memory/linear/issues.json
```

Imported issues become Markdown tasks under `.agents/tasks/linear/` and are indexed for `tasks check`.

Commit:

- `config.yaml`
- `.gitignore`
- this README
- `knowledge/**/*.md`
- `rationale/**/*.md`
- `evals/**/*.jsonl`
- `human/**/*.md` when the module is enabled

Do not commit:

- `graph.sqlite`
- `qdrant/`
- `logs/`
- `reports/`
- `cache/`
- `models/`
- `tmp/`
