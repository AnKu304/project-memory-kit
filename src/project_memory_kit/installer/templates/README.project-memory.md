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
./pmem tasks check
./pmem tests --base HEAD --explain
./pmem watch --once
```

Optional modules are controlled in `config.yaml`:

```yaml
modules:
  human:
    enabled: false
```

`human` is disabled by default. Enabling it creates `human/`; disabling it keeps existing files.

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
