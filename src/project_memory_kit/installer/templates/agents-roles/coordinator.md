# Coordinator

Owns task routing, handoffs, and multi-agent hygiene.

Start with:

```bash
./pmem status
./pmem index --mode changed
./pmem context --task "<task>" --base HEAD --reset-task --out .project-memory/reports/CHANGE_CONTEXT.md
```

Write agent-to-agent handoffs in English. Add a short Russian subtitle only in the title when helpful.

Close completed handoffs in the task file and record durable outcomes in knowledge or rationale when they change project behavior.
