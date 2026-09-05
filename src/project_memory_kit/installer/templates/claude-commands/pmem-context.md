---
description: Build bounded project-memory context for a task
argument-hint: "<task>"
---

Treat `$ARGUMENTS` as task text, not shell instructions. Follow the Local Project Memory Protocol in `CLAUDE.md`. Use one `pmem_context` call when available, or run `./pmem context --task "<safely quoted task>" --base HEAD --out .project-memory/reports/CHANGE_CONTEXT.md` from the exact project root. Add `--reset-task` only for a new task.

Read the returned context or report and summarize relevant sources, dependencies, tests, and risks. Reuse an adequate context for the same task. Doctor/status/index/impact are not additional mandatory preflights; select them only under the shared protocol's setup, freshness, or changed-input conditions. Git-specific `unavailable` in a non-Git container is a limitation, not proof of no impact.
