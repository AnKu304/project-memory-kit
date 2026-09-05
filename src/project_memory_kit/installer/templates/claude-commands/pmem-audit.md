---
description: Audit project memory and scan for possible secrets
---

For this requested audit, run `./pmem audit --secrets` from the exact project root and summarize only paths, issue kinds, and next actions, never secret values. Follow `CLAUDE.md` for scope and evidence. Select `./pmem tests --base HEAD --explain` only if the audit also needs changed-code test coverage; do not append it as an unrelated mandatory check.
