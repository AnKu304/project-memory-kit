# Project Memory

This directory stores local Dependency Graph RAG state.

Vector state is controlled by `config.yaml`:

- `vector.backend: auto` tries Qdrant local + FastEmbed and falls back offline.
- `vector.backend: qdrant` requires Qdrant/FastEmbed and fails loudly if unavailable.
- `vector.backend: fallback` keeps deterministic bootstrap records only.

Commit:

- `config.yaml`
- `.gitignore`
- this README

Do not commit:

- `graph.sqlite`
- `qdrant/`
- `logs/`
- `reports/`
- `cache/`
- `models/`
- `tmp/`
