# Changelog

## 0.22.0

Added:

- Multi-chat Write Concurrency: безопасная запись из нескольких чатов.
- SQLite `busy_timeout` on every runtime connection.
- Managed write lock with metadata, TTL, stale cleanup, and `pmem lock status/clear`.
- Local write queue with `pmem queue list/drain/clear`.
- Optional Qdrant server URL through `vector.url`.

Updated:

- Write commands are serialized; read commands stay parallel.
- Busy write commands are queued instead of failing immediately.
- Auto-index locks now store metadata and clean stale locks.
- Config schema includes `concurrency.*`, `paths.runtime_dir`, and `vector.url`.

Removed:

- Nothing.

Better than 0.21.0:

- Two or three chats can use the same project memory without corrupting local state.
- Existing projects upgrade in place: SQLite database, Qdrant state, knowledge, rationale, Human files, logs, and reports are preserved.
- Teams can keep embedded local Qdrant or switch to a local Qdrant server for more robust multi-process vector access.

## 0.21.0

Added:

- Depth Improvements.
- Глубинные улучшения.
- `./pmem context --compiled`.
- Built-in golden evals for indexed Python, JS/TS, mixed, and Next-route projects.
- Local evidence, task gates, memory lifecycle, and provenance sections in compiled context.

Updated:

- Search now applies deterministic diversity and lifecycle penalties for superseded/archived memory records.
- Impact analysis now uses test-to-source graph bindings and surfaces graph confidence in affected-test reasons.
- JS/TS indexing now records local test bindings for `.test` / `.spec` files.

Removed:

- Nothing.

Better than 0.20.0:

- Agents get one bounded, evidence-backed task packet instead of manually stitching together many local reports.
- Retrieval is less repetitive and less likely to surface stale memory as a top result.
- Test selection is more accurate for JS/TS projects with colocated test files.

## 0.20.0

Added:

- CI Runtime Warning Cleanup.
- Очистка предупреждений CI.

Updated:

- GitHub Actions now uses Node 24-capable actions: `actions/checkout@v6`, `actions/setup-python@v6`, and `actions/setup-node@v6`.
- CI opts into the JavaScript action Node 24 runtime with `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`.
- The Node test matrix now covers Node 22 and Node 24.

Removed:

- Node 20 from the CI test matrix.

Better than 0.19.0:

- CI no longer depends on deprecated Node 20 action runtimes.
- The workflow tests current Node LTS/current runtime paths while keeping the Python 3.11/3.12 matrix.

## 0.19.0

Added:

- MCP Task Write Tools.
- MCP-инструменты для записи задач.
- `pmem_tasks_create`, `pmem_tasks_assign`, and `pmem_tasks_close`.

Updated:

- MCP task tools can now create local `.agents/tasks/` Markdown handoffs, update task roles, and close completed tasks.
- Task write tools are marked as non-read-only in MCP annotations.

Removed:

- Nothing.

Better than 0.18.0:

- MCP-connected agents can coordinate task handoffs without manually editing Markdown files.
- Created and updated tasks are re-indexed locally, so other chats can find the latest state through project memory.

## 0.18.0

Added:

- Install Wizard.
- Мастер установки.
- `pmem init --interactive` and `pmem install --interactive`.

Updated:

- Interactive install can choose the agent profile, multi-agent task templates, Human layer, vector backend, and MCP config.
- Non-interactive install and upgrade behavior stays unchanged.

Removed:

- Nothing.

Better than 0.17.0:

- New projects can be bootstrapped with fewer flags and fewer missed optional settings.
- The wizard remains script-testable through stdin choices.

## 0.17.0

Added:

- Human Graph Viewer.
- Визуальный просмотр графа Human-слоя.
- `./pmem human graph --html`.
- Static local `graph.html` with layer/type/status filters and search.

Updated:

- Human graph JSON now includes note status for filtering.

Removed:

- Nothing.

Better than 0.16.0:

- The Human layer can be inspected visually without running a server or installing extra packages.
- Users and agents can filter the human-readable memory graph before opening full notes.

## 0.16.0

Added:

- Memory Quality Dashboard.
- Панель качества памяти.
- `./pmem report` with Markdown output.
- `./pmem report --format json`.

Updated:

- Reports summarize index freshness, graph counts, knowledge/rationale conflicts, active tasks, eval hints, and module state.

Removed:

- Nothing.

Better than 0.15.0:

- Agents can check memory health with one compact local command before work.
- The report avoids loading large files or logs into model context.

## 0.15.0

Added:

- TS/Next Graph Depth.
- Глубина графа TypeScript/Next.js.
- Route-to-component graph edges for Next.js app routes.
- Client/server component boundary metadata from `use client` and app-route defaults.
- HTTP method metadata for Next.js `route.ts/js` files.
- JS/TS route impact details in impact reports.

Updated:

- Next route nodes now connect to local route components and imported JSX components when bindings are available.
- File and symbol nodes can include component boundary metadata.

Removed:

- Nothing.

Better than 0.14.0:

- Agents get more accurate frontend dependency context before editing Next.js pages or API routes.
- Impact reports show route-level meaning instead of only changed file paths.

## 0.14.0

Added:

- Real File Watcher.
- Настоящий локальный наблюдатель файлов.
- `./pmem watch --serve` for an explicit long-running local polling watcher.

Updated:

- `./pmem watch` now performs one safe check by default instead of starting an unbounded loop.
- Watch output includes numbered checks.
- Existing `--interval` and `--max-runs` behavior is preserved for bounded watcher runs.

Removed:

- Nothing.

Better than 0.13.0:

- Agents can keep the local index fresh during work without relying on chat context.
- Running `./pmem watch` directly no longer risks an accidental infinite command.

## 0.13.0

Added:

- Linear Sync.
- Синхронизация задач с Linear.
- `./pmem tasks linear status`, `export`, and `import`.
- Optional `integrations.linear` config with a local bridge directory.
- JSON bridge format for exporting `.agents/tasks/` and importing Linear issues back into Markdown task files.

Updated:

- Imported Linear tasks are written under `.agents/tasks/linear/` and re-indexed automatically.
- Installer metadata now lists `.project-memory/linear/` as preserved local state.

Removed:

- Nothing.

Better than 0.12.0:

- Multi-chat task coordination can now connect to Linear without adding a required Linear API dependency.
- `.agents/tasks/` stays usable as the local source of truth when Linear is not configured.

## 0.12.0

Added:

- Bidirectional Human Sync.
- Двусторонняя синхронизация Human-слоя.
- `./pmem human sync` now pulls manual edits from generated Human notes back into source `knowledge` or `rationale` records.
- Human notes now include source and body hash metadata for sync safety.
- Conflict detection when both a Human note and its source memory record changed after export.

Updated:

- Human export keeps sync metadata in generated Markdown frontmatter.
- Human sync regenerates and re-indexes the Human layer after successful source updates.

Removed:

- Nothing.

Better than 0.11.0:

- The Human layer is no longer export-only.
- Manual edits in the human-readable layer can become durable project memory.
- Conflicting edits are visible instead of being overwritten silently.

## 0.11.0

Added:

- Optional Human/Obsidian-like Markdown layer.
- `./pmem human status`, `./pmem human export`, `./pmem human sync`, `./pmem human search`, and `./pmem human graph`.
- Generated Human files under `.project-memory/human/` with frontmatter, source links, backlinks, `index.md`, `graph.mmd`, and `graph.json`.
- `./pmem search --layer human`.
- MCP tools: `pmem_human_status`, `pmem_human_export`, `pmem_human_search`, and `pmem_human_graph`.
- `./pmem tasks close --file ... --summary ...`.
- Catch-up checklist under `docs/checklists/v0.11.0-catch-up.md`.

Updated:

- Multi-agent task lifecycle now has an explicit close action.
- Completed task files are re-indexed after close.
- Human generated files remove stale generated notes on export/sync.
- MCP tool schemas moved into `mcp_tools.py` to keep `mcp.py` small enough for code-bloat guards.

Removed:

- Nothing.

Better than 0.10.0:

- The previously placeholder Human module now has real behavior.
- Users can inspect project memory in a human-readable Markdown graph view.
- Multi-chat task handoffs can be closed locally instead of lingering as active work.

## 0.10.0

Added:

- `npm run smoke` for package-level wrapper and install smoke checks.
- `npm run pack:check` for tarball content validation.
- npm `prepack` smoke check.
- npm distribution guide under `docs/npm.md`.
- CI steps for npm smoke and package content validation.

Updated:

- npm package version moved to `0.10.0`.
- npm `files` list now includes only required source, runtime, templates, docs, and wrapper files.
- Node wrapper now verifies Python 3.11+ before running the CLI.
- Package metadata now includes `bugs`, `type: commonjs`, and public scoped publish config.

Removed:

- Generated Python cache files are excluded from the npm package.

Better than 0.9.0:

- npm packaging is publish-ready apart from the final authenticated `npm publish`.
- Package content is validated automatically.
- Users get a clear error when Python is missing or too old.

## 0.9.0

Added:

- `.agents/tasks/` templates for user tasks and agent-to-agent handoff tasks.
- `./pmem tasks check` and `./pmem tasks list` for active multi-agent task checks.
- MCP tool `pmem_tasks`.
- Claude MCP config writer through `./pmem mcp-config --client claude --write`.
- Secret audit detection for JWT-like tokens and high-entropy assigned values.
- Secret audit allowlist support through `.project-memory/config.yaml`.
- JS/TS workspace/package alias resolution for imports such as `@acme/ui/button`.
- Next.js app route metadata during indexing.
- Eval fixture templates under `.project-memory/evals/`.
- Claude project security settings template in `.claude/settings.json`.
- Quality guard tests for version sync, README/CHANGELOG sync, and config schema sync.

Updated:

- Upgrade can add a new profile while preserving already installed profiles and memory databases.
- Installer metadata now records `agent_profiles` and managed paths.
- Multi-agent profile now includes shared rules and task templates.
- `./pmem watch` can run as a bounded loop with `--interval` and `--max-runs`.
- Config schema is now `7` and audit settings include entropy threshold and allowlist.
- Agent instructions now tell agents to check active tasks before editing.

Removed:

- Nothing.

Better than 0.8.0:

- Upgrades are safer when moving from Codex-only to Claude or multi-agent.
- JS/TS/Next projects get better dependency and route context before edits.
- Multi-chat projects have a local task surface instead of relying only on chat history.
- MCP setup is less manual for Claude-compatible clients.
- Secret checks are more useful and less noisy.

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
