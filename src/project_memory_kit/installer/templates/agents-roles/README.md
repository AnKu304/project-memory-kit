# Multi-Agent Roles

Use these role notes when several chats or agents work on the same repository.

Agent-to-agent task notes are written in English. A short Russian subtitle may be added to the task title so the project owner can scan the queue quickly.

Follow the shared Local Project Memory Protocol in `AGENTS.md`/`CLAUDE.md`. Read active handoffs with `./pmem tasks check` when `.agents/tasks/` exists, and use one bounded context or reuse the current task context. Roles do not add doctor/status/impact or unconditional indexing sequences. Refresh only stale/changed inputs as the shared protocol requires.

MCP knowledge/rationale add/update use an existing project-relative source file; CLI is the fallback within the role's tools. Verify saved/completed/record then show/search. Queued/busy means pending. Scope, permissions, and handoffs remain separate from memory labels.

If the task belongs to another role, say which role should handle it and stop after creating or updating the handoff note.

Suggested roles:

- `coordinator`: routes work and keeps handoffs clean.
- `researcher`: studies references, product behavior, SEO, UX, design, architecture, and mechanics.
- `implementer`: edits code within a scoped task.
- `reviewer`: checks impact, tests, memory quality, and secret safety.
