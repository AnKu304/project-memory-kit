# Agent Rules

The local project-memory workflow is mandatory for meaningful code and knowledge work.

Use `./pmem knowledge context --task "<task>"` for research, architecture, SEO, UX, design, product, content, positioning, or principle-heavy tasks.

Use `./pmem rationale context --task "<task>"` for "why", rejected approaches, architecture decisions, tool choices, repeated dead ends, experiments, and invariants.

Use `./pmem knowledge update` when durable project principles change. Retire obsolete entries instead of keeping conflicting current records.

Use `./pmem rationale update` when durable causes or rejected alternatives change. Retire obsolete rationale instead of keeping conflicting current explanations.

Keep model context bounded. Inspect large files, logs, reports, and test output through local tools first. Bring only relevant findings, short excerpts, ids, and paths into the working context. Open or transmit full documents and long logs only when the bounded local workflow is insufficient.

Rationale records must contain verified decisions, alternatives, and evidence. Do not store hidden chain-of-thought.

External skills installed in `.agents/skills/` may help with domain-specific work, but they do not replace the memory workflow.

Never index secrets, credentials, tokens, private keys, `.env` files, dependency directories, build outputs, caches, or binary files.
