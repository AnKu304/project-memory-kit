# AGENTS.md

Machine instructions for agents working on `project-memory-kit`.

## Scope

These instructions apply to the whole repository.

## Project Shape

- This repository builds the installer package.
- Installed runtime files are copied from `src/project_memory_kit/installer/runtime/tools/project_memory/`.
- Installed skill files are copied from `src/project_memory_kit/installer/skill/dependency-graph-rag/`.
- Installed project templates are copied from `src/project_memory_kit/installer/templates/`.
- Do not edit generated temp installs as source. Edit the installer source, runtime source, skill source, or templates.

## Required Context

Before changing code or docs, read the relevant files:

- `README.md`
- `README.en.md`
- `pyproject.toml`
- relevant files under `src/project_memory_kit/installer/`
- relevant tests under `tests/`

Keep `README.md` and `README.en.md` synchronized when changing user-facing documentation.

## Editing Rules

- Keep the project local-first and dependency-light.
- Do not add mandatory runtime dependencies unless the user explicitly asks for them.
- Prefer optional backends with clear fallback behavior.
- Keep installer behavior safe for existing repositories: preserve user files and update only managed blocks.
- Do not make `pmem` manage unrelated external skills.
- Keep AGENTS template changes separate from this repository's root `AGENTS.md`.
- Do not store or index secrets in examples, tests, or generated files.

## Testing

Run the main test suite after meaningful changes:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:src/project_memory_kit/installer/runtime python3 -m unittest discover -s tests
```

For installer smoke tests, always use a temporary directory.

For GitHub install verification, use `--no-cache`:

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target <temp-repo>
```

Never install this package into the repository root as a smoke test.

## Git

- Do not commit runtime state from `.project-memory/`.
- Do not commit generated temp repositories.
- Before committing, run `git diff --check` and inspect `git status --short`.


<!-- PMEM:BEGIN -->
## Local Project Memory Protocol

This repository uses local Dependency Graph RAG project memory.

The memory system is installed in:

```text
.project-memory/
tools/project_memory/
.agents/skills/dependency-graph-rag/
.agents/rules/
```

If the local MCP server is configured, use the equivalent `pmem_*` tools for bounded context, search, impact, tests, knowledge, and rationale. The CLI commands below remain the fallback and verification baseline.

Before any meaningful code, config, schema, dependency, API, test, build, routing, migration, auth, persistence, or architecture change, run:

```bash
./pmem doctor
./pmem status
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "<current task>" --base HEAD --reset-task --out .project-memory/reports/CHANGE_CONTEXT.md
```

Read `.project-memory/reports/CHANGE_CONTEXT.md` before editing. Identify target files, target symbols, direct dependencies, reverse dependencies, affected tests, related previous failures, architecture constraints, and low-confidence graph areas.

If `.agents/tasks/` exists, check active user tasks and handoffs before starting:

```bash
./pmem tasks check
```

When a task file has been completed, close it instead of leaving it active:

```bash
./pmem tasks close --file "<task md path>" --summary "<what changed>"
```

Keep context bounded. Use local tools to inspect large files, logs, reports, and test output. Bring only relevant findings, short excerpts, ids, and paths into the working context. Open full files, full knowledge/rationale notes, or long logs only when local summaries are insufficient.

For research, product, UX, design, SEO, architecture, content, positioning, or other principle-heavy work, also run:

```bash
./pmem knowledge context --task "<current task>" --out .project-memory/reports/KNOWLEDGE_CONTEXT.md
```

Read `.project-memory/reports/KNOWLEDGE_CONTEXT.md` and open the referenced full Markdown files before relying on a research note or project principle.

For tasks involving "why", rejected approaches, architecture choices, storage choices, tool choices, prior failures, or repeated dead ends, also run:

```bash
./pmem rationale context --task "<current task>" --out .project-memory/reports/RATIONALE_CONTEXT.md
```

Read `.project-memory/reports/RATIONALE_CONTEXT.md` before repeating an approach. Rationale stores verified decisions, rejected alternatives, and evidence; never use it to store hidden chain-of-thought.

After editing, run:

```bash
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem tests --base HEAD --explain
```

Run the targeted test commands returned by `./pmem tests --base HEAD`.

If retrieved memory looks incomplete or surprising, run:

```bash
./pmem search --query "<task terms>" --debug
```

For memory quality checks, run:

```bash
./pmem stale
./pmem audit
./pmem audit --secrets
./pmem eval --file .project-memory/evals/search.jsonl
```

Use project-local tooling and sandboxes for verification whenever possible. Inspect command output locally and summarize the relevant result; do not send long raw outputs unless they are necessary to diagnose an ambiguous failure.

Multiple chats may read project memory at the same time. Write commands are serialized by a local write lock. If a write command reports `queued write`, do not assume the memory update has been applied; tell the user and run or ask for:

```bash
./pmem lock status
./pmem queue list
./pmem queue drain
```

Use `./pmem lock clear` only for stale locks. Use `./pmem lock clear --force` only when the writer process is known to be stopped.

`./pmem watch --serve` is allowed as a background freshness helper, but it must not be treated as a reason to wait on memory. Auto-index may skip a pass when another writer is active; continue with the current index and run `./pmem index --mode changed` after the writer finishes.

Embedded local Qdrant is guarded by `qdrant.lock`. If vector access is busy, prefer the SQLite/BM25 results already returned by `pmem search/context` instead of retrying in a loop. For heavy parallel chat work, configure a local Qdrant server through `vector.url`.

When a durable research finding, architecture note, SEO rule, design principle, UX rule, product mechanic, or content rule changes, update project knowledge:

```bash
./pmem knowledge add --type "<research|architecture|seo|design|ux|product|decision>" --title "<title>" --file "<markdown file>"
./pmem knowledge update --id "<knowledge id>" --file "<markdown file>"
```

Use `knowledge update` for changed principles. Use `knowledge retire` for obsolete entries. Do not keep two competing `current` records for the same rule.

When a durable decision, rejected approach, experiment result, invariant, or cause changes, update project rationale:

```bash
./pmem rationale add --type "<decision|rejection|experiment|constraint>" --title "<title>" --file "<markdown file>"
./pmem rationale update --id "<rationale id>" --file "<markdown file>"
```

Use `rationale update` for changed causes. Use `rationale retire` for obsolete explanations. Do not keep two competing `current` rationales for the same decision.

If the optional human layer is enabled, refresh it after durable knowledge or rationale changes:

```bash
./pmem human export
./pmem human graph
```

If a test fails:

```bash
mkdir -p .project-memory/logs
./pmem record-failure --command "<failed command>" --log-file "<log path>"
./pmem context --task "fix failing tests after current change" --base HEAD --out .project-memory/reports/CHANGE_CONTEXT.md
```

Final responses after code changes must include files changed, symbols changed, impact checked, tests run, knowledge/rationale updates if any, failure memory updates, and remaining risk.

External skills may also exist in `.agents/skills/`. Use them when relevant, but they do not replace this mandatory project-memory protocol.

Additional project rules may exist in `.agents/rules/`.

Never index, print, or store secrets.
<!-- PMEM:END -->
