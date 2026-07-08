---
description: Build bounded project-memory context for a task
argument-hint: "<task>"
---

Use the provided task text as `$ARGUMENTS`.

```bash
./pmem doctor
./pmem status
./pmem impact --base HEAD --format markdown
./pmem context --task "$ARGUMENTS" --base HEAD --reset-task --out .project-memory/reports/CHANGE_CONTEXT.md
```

Run `./pmem index --mode changed` before rebuilding context only when status shows stale task-relevant files or the report looks incomplete.

Read `.project-memory/reports/CHANGE_CONTEXT.md` and summarize only the relevant files, symbols, dependencies, tests, and risks.
