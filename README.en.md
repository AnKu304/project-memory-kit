# project-memory-kit

Russian version: [README.md](README.md)

`project-memory-kit` adds local project memory for coding agents.

The memory lives inside the repository, so several chats can work on the same project without losing context. Agents can inspect files, symbols, imports, reverse dependencies, relevant tests, and previous failures before editing.

## What It Installs

```text
AGENTS.md
.agents/skills/dependency-graph-rag/
.project-memory/config.yaml
.project-memory/.gitignore
.project-memory/README.md
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

Check the install:

```bash
./pmem doctor
./pmem index --mode full
```

## Agent Workflow

Before editing:

```bash
./pmem doctor
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "<task>" --base HEAD --out .project-memory/reports/CHANGE_CONTEXT.md
```

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
pmem uninstall --target . --keep-memory
pmem uninstall --target . --purge
```

Installed runtime:

```bash
./pmem doctor
./pmem index --mode full
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "task description"
./pmem tests --base HEAD
./pmem search --query "payment validation" --limit 10
./pmem record-failure --command "npm test" --log-file ".project-memory/logs/test.log"
```

## How It Works

- SQLite stores the project graph: files, symbols, chunks, imports, calls, inheritance, failures.
- SQLite FTS provides baseline chunk search.
- Qdrant local + FastEmbed provide semantic search when available.
- If Qdrant/FastEmbed are not available, deterministic fallback keeps install and indexing usable.
- The Python parser extracts modules, classes, functions, methods, imports, calls, inheritance, and docstrings.
- The JS/TS parser extracts modules, classes, functions, methods, imports, exports, require, dynamic imports, calls, and JSX component references.
- JS/TS uses the TypeScript compiler API when `node` and `typescript` are available in the project; otherwise it uses the built-in lexical parser.
- Secrets, `.env` files, dependency directories, build outputs, caches, and binary files are not indexed.

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
