# Agent Tasks

This folder is for explicit user tasks and agent-to-agent handoffs.

Agents should check active tasks before starting:

```bash
./pmem tasks check
```

Task files are written in English. A short Russian subtitle may be added to the title when it helps the project owner scan the queue.

Close completed tasks by changing `Status: active` to `Status: done`, `closed`, or `cancelled`.
