# project-memory-kit

Russian version: [README.md](README.md)

`project-memory-kit` adds local project memory for coding agents.

The memory lives inside the repository, so several chats can work on the same project without losing context. Agents can inspect files, symbols, imports, reverse dependencies, relevant tests, previous failures, and durable project principles before editing.

## What It Installs

```text
AGENTS.md
.agents/skills/dependency-graph-rag/
.project-memory/config.yaml
.project-memory/.gitignore
.project-memory/README.md
.project-memory/install.json
.project-memory/knowledge/
.project-memory/rationale/
tools/project_memory/
pmem
pmem.ps1
.gitignore
```

If `AGENTS.md` already exists, the installer preserves user content and updates only the managed block:

```text
<!-- PMEM:BEGIN -->
...
<!-- PMEM:END -->
```

External skills are not managed by this project. Install them separately and document when to use them in `AGENTS.md`.

## Install

From the target repository root:

```bash
pipx run --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target .
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
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem upgrade --target .
```

Upgrade refreshes managed files and runs migrations. Databases and runtime state under `.project-memory/` are preserved.

## Agent Workflow

Before editing:

```bash
./pmem doctor
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
pmem install --target .
pmem upgrade --target .
pmem upgrade --target . --with-vector
pmem uninstall --target . --keep-memory
pmem uninstall --target . --purge
pmem version
```

Installed runtime:

```bash
./pmem version
./pmem doctor
./pmem migrate
./pmem modules list
./pmem modules set human --enabled true
./pmem modules set human --enabled false
./pmem index --mode full
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "task description"
./pmem knowledge add --type research --title "Resource mechanics" --file notes/research.md
./pmem knowledge update --id resource-mechanics --file notes/research.md
./pmem knowledge search --query "SEO rules"
./pmem knowledge context --task "redesign product page"
./pmem knowledge show --id resource-mechanics
./pmem knowledge retire --id old-design-rules
./pmem rationale add --type decision --title "Use SQLite" --file notes/rationale/sqlite.md
./pmem rationale update --id use-sqlite --file notes/rationale/sqlite.md
./pmem rationale search --query "why not postgres"
./pmem rationale context --task "change memory database"
./pmem rationale show --id use-sqlite
./pmem rationale retire --id old-storage-choice
./pmem tests --base HEAD
./pmem search --query "payment validation" --limit 10
./pmem search --query "pricing SEO" --layer knowledge
./pmem search --query "why sqlite" --layer rationale
./pmem record-failure --command "npm test" --log-file ".project-memory/logs/test.log"
./pmem mcp --root .
```

## Local MCP

`./pmem mcp` starts a local stdio MCP server over the same runtime and the same `.project-memory/` database. It does not create separate memory and does not send data to an external service.

Example MCP client config:

```toml
[mcp_servers.project_memory]
command = "/absolute/path/to/repo/pmem"
args = ["mcp", "--root", "/absolute/path/to/repo"]
```

Available MCP tools:

```text
pmem_doctor
pmem_index
pmem_context
pmem_impact
pmem_tests
pmem_search
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
- SQLite FTS5 `bm25()` ranks keyword results. Vector search is added on top when Qdrant/FastEmbed are available.
- `search`, `context`, `impact`, and `tests` automatically run a local `changed` index when the database is empty or stale.
- Full records are opened only when needed.
- Edges have `confidence`; more exact bindings receive higher scores.
- Qdrant local + FastEmbed provide semantic search when available.
- If Qdrant/FastEmbed are not available, deterministic fallback keeps install and indexing usable.
- The Python parser extracts modules, classes, functions, methods, imports, calls, inheritance, and docstrings.
- The JS/TS parser extracts modules, classes, functions, methods, imports, exports, require, dynamic imports, calls, and JSX component references.
- JS/TS uses the TypeScript compiler API when `node` and `typescript` are available in the project; otherwise it uses the built-in lexical parser.
- A local MCP server exposes doctor/index/context/impact/search/tests/knowledge/rationale tools over the same `pmem` runtime.
- Secrets, `.env` files, dependency directories, build outputs, caches, and binary files are not indexed.

## Optional Modules

Modules are configured in `.project-memory/config.yaml`.

```yaml
modules:
  human:
    enabled: false
```

`human` is disabled by default. Enabling it creates `.project-memory/human/`; disabling it does not delete data:

```bash
./pmem modules list
./pmem modules set human --enabled true
./pmem modules set human --enabled false
```

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
