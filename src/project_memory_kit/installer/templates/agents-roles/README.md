# Multi-Agent Roles

Use these role notes when several chats or agents work on the same repository.

Agent-to-agent task notes are written in English. A short Russian subtitle may be added to the task title so the project owner can scan the queue quickly.

Each agent should check active handoffs before starting:

```bash
find .agents/tasks -type f -name "*.md" 2>/dev/null | sort
./pmem status
```

Run `./pmem index --mode changed` at intake only when status/context shows stale task-relevant files or incomplete retrieval. It remains required after meaningful edits.

If the task belongs to another role, say which role should handle it and stop after creating or updating the handoff note.

Suggested roles:

- `coordinator`: routes work and keeps handoffs clean.
- `researcher`: studies references, product behavior, SEO, UX, design, architecture, and mechanics.
- `implementer`: edits code within a scoped task.
- `reviewer`: checks impact, tests, memory quality, and secret safety.
