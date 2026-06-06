# Project Memory

This directory stores local Dependency Graph RAG state.

Project knowledge lives in `knowledge/`. These Markdown files are the full source for research notes, architecture decisions, SEO rules, design principles, UX rules, product mechanics, and other durable project context.

Project rationale lives in `rationale/`. These Markdown files are the full source for verified decisions, rejected alternatives, experiments, invariants, and evidence-backed "why" records.

Vector state is controlled by `config.yaml`:

- `vector.backend: auto` tries Qdrant local + FastEmbed and falls back offline.
- `vector.backend: qdrant` requires Qdrant/FastEmbed and fails loudly if unavailable.
- `vector.backend: fallback` keeps deterministic bootstrap records only.

Commit:

- `config.yaml`
- `.gitignore`
- this README
- `knowledge/**/*.md`
- `rationale/**/*.md`

Do not commit:

- `graph.sqlite`
- `qdrant/`
- `logs/`
- `reports/`
- `cache/`
- `models/`
- `tmp/`
