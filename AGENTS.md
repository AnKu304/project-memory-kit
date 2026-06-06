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
