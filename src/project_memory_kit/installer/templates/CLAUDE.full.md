# CLAUDE.md

This file is the project instruction hub for Claude Code.

Keep stable repository rules here. If a section grows too large, move the detailed rules into a separate Markdown file and import it from this file.

## Project Context

<!-- USER EDITABLE: describe what this project does, who uses it, and which product/domain constraints matter. -->

Before planning meaningful work, review these files when they exist:

- `README.md`
- `PROJECT_RULES.md`
- `TASK.md`
- `RULES.md`
- `AGENTS.md`

Add or remove files from this list to match the project.

## Project Rules

<!-- USER EDITABLE: add coding conventions, architecture rules, dependency rules, security rules, deployment rules, and review expectations. -->

Suggested examples:

- Prefer existing project patterns over new abstractions.
- Keep changes scoped to the task and documented impact.
- Do not store secrets, credentials, tokens, or private keys in memory, logs, docs, or Git.
- If extra rules live in `PROJECT_RULES.md` or `RULES.md`, read them before editing.

## Claude Project Skills

<!-- USER EDITABLE: document when to use project-specific skills under `.claude/skills/`. -->

Project skills may exist in `.claude/skills/`. Use them when relevant, but they do not replace the mandatory project-memory protocol below.

## Local Project Memory

The following block is managed by `project-memory-kit`.
