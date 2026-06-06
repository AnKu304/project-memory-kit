# AGENTS.md

This file is the project instruction hub for Codex and other coding agents.

Keep stable repository rules here. If a section grows too large, move the detailed rules into a separate Markdown file and link it from this file.

## Project Context

<!-- USER EDITABLE: describe what this project does, who uses it, and which product/domain constraints matter. -->

Before planning meaningful work, review these files when they exist:

- `README.md`
- `PROJECT_RULES.md`
- `TASK.md`
- `RULES.md`

Add or remove files from this list to match the project.

## Project Rules

<!-- USER EDITABLE: add coding conventions, architecture rules, dependency rules, security rules, deployment rules, and review expectations. -->

Suggested examples:

- Prefer existing project patterns over new abstractions.
- Keep changes scoped to the task and documented impact.
- Do not store secrets, credentials, tokens, or private keys in memory, logs, docs, or Git.
- If extra rules live in `PROJECT_RULES.md` or `RULES.md`, read them before editing.

## External Skills

<!-- USER EDITABLE: document when to use project-specific external skills installed separately with tools such as `npx skills add`. -->

External skills may exist in `.agents/skills/`. Use them when relevant, but they do not replace the mandatory project-memory protocol below.

Examples to customize or delete:

- Use `$frontend-design` for UI creation, redesign, and UX-heavy frontend work.
- Use `$next-best-practices` for Next.js routing, rendering, and performance work.
- Use `$shadcn` when adding or changing shadcn/ui components.
- Use `$pdf` or `$documents` for PDF, DOCX, or document-processing tasks.

## Local Project Memory

The following block is managed by `project-memory-kit`.

