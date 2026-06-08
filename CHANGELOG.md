# Changelog

## 0.8.0

Added:

- npm/npx distribution with `@anku/project-memory-kit` package metadata and a `pmem` Node wrapper.
- Install profiles: `Codex` by default, optional `Claude`, and optional `Multi-agent`.
- Claude Code project structure: `CLAUDE.md`, `.claude/rules/project-memory.md`, `.claude/skills/dependency-graph-rag/`, and `.claude/commands/`.
- Multi-agent role structure: `.agents/roles/` and `.claude/agents/`.
- `./pmem audit --secrets` for local possible-secret detection without printing matched secret values.
- `./pmem optimize` for local SQLite maintenance.
- `./pmem mcp-config` to print a ready MCP client config snippet.
- GitHub Actions CI for unit tests, installer smoke checks, and npm wrapper smoke checks.
- Code bloat guard tests for oversized Python functions and files.
- Release notes under `docs/release-notes/`.

Updated:

- `pmem upgrade --agent auto` preserves the previous install profile when possible.
- Installer metadata now records `agent_profile`.
- Config schema is now `6` and includes audit secret-scan limits.
- Documentation now covers npm/npx, install profile selection, Claude structure, Multi-agent structure, and release workflow.
- Package version fields are synchronized across Python package metadata, runtime, and npm metadata.

Removed:

- Nothing.

Better than 0.7.0:

- JS/TS/Next/React projects can bootstrap through `npx` as well as `pipx`.
- Claude Code users get a native project structure instead of Codex-only `AGENTS.md`.
- Multi-agent projects can start from a shared universal structure instead of ad hoc folders.
- Upgrade remains memory-safe while adding or preserving agent profiles.
- Local checks now cover possible secrets, SQLite maintenance, and generated MCP config.

## 0.7.0

Added:

- Hybrid Search v2 with BM25, vector, term, path, graph, confidence, layer, and recency scoring.
- `./pmem search --debug` to show ranking components.
- `./pmem status` for index freshness, graph counts, vector state, parser config, and module state.
- `./pmem stale` for a compact stale/missing/removed index report.
- `./pmem eval` for local JSONL memory evals.
- `./pmem audit` for memory governance checks.
- `./pmem tests --explain` for test-selection reasons and recent failure fingerprints.
- `./pmem watch --once` for one-shot local auto-index checks.
- MCP tools: `pmem_status`, `pmem_search_debug`, `pmem_eval`, `pmem_audit`, `pmem_modules`, `pmem_watch_status`.
- Optional JS/TS parser backend config for `auto`, `typescript`, `tree_sitter`, `lsp`, and `lexical`.
- `.project-memory/evals/` as a commit-safe place for memory eval files.

Updated:

- Search results are now ranked by a hybrid score instead of BM25/vector candidates sorted separately.
- Auto-index config includes `watch`.
- Test selection can now explain why commands were chosen.
- Documentation now includes versioned release notes and new commands.

Removed:

- Nothing.

Better than 0.6.0:

- Agents can inspect why memory results were returned.
- Projects can measure memory quality with local evals.
- Stale index state is visible before work starts.
- MCP clients can use the same diagnostics as the CLI.
- JS/TS parser extensibility is prepared without adding mandatory dependencies.

## 0.6.0

Added:

- SQLite FTS5 BM25 keyword ranking.
- Auto-index freshness checks for `search`, `context`, `impact`, and `tests`.
- Cleanup for deleted file chunks and file index state.
- Optional module config with `human` disabled by default.
- `./pmem modules list`.
- `./pmem modules set human --enabled true|false`.

Updated:

- `changed` indexing now includes git untracked files.
- README files document BM25, auto-indexing, and optional modules.

Removed:

- Nothing.

Better than 0.5.0:

- Keyword search is more accurate.
- Agents can search before running manual index.
- Deleted files stop appearing in search.
- Optional human-facing memory can be enabled without changing the core runtime.

## 0.5.0

Added:

- Local stdio MCP server through `./pmem mcp --root .`.
- MCP tools for doctor, index, context, impact, tests, search, knowledge, rationale, and failure recording.

Updated:

- Documentation includes local MCP setup.

Removed:

- Nothing.

Better than 0.4.x:

- Agents can access project memory through MCP without creating a second memory store.
