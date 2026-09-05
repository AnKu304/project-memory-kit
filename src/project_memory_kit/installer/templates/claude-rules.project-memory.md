# Project Memory Rules

Follow the shared **Local Project Memory Protocol** in `CLAUDE.md` (and `AGENTS.md` when present). Use the same exact project root and local database. These rules do not add a second startup sequence or expand the task.

Start a meaningful task with one `pmem_context` or CLI context, then inspect the relevant sources. Reuse that context during the task; reset only for a new task. Doctor is for setup/runtime changes/malfunction, status for uncertain freshness. Refresh stale or changed indexed sources once, unless auto-index already verified the same inputs. Do not automatically repeat impact, knowledge/rationale context, or unchanged green checks.

For research, principles, prior decisions, and failures, open relevant records by ID and verify their sources. Add targeted knowledge/rationale context only for a gap in the initial result. Keep one current record per principle or explanation; update or retire obsolete records. Rationale contains verified reasons, alternatives, and evidence, never hidden chain-of-thought.

When available, `pmem_knowledge_add/update` and `pmem_rationale_add/update` write from an existing project-relative file under the same MCP root; CLI add/update is the fallback. Confirm `saved`, `completed: true`, and the returned record, then show/search. A queued or busy result is pending; inspect lock/queue state and drain only expected authorized operations after the writer finishes. Do not clear live locks or retry uncertain writes blindly. Omitted `links` on update preserves relations; `[]` clears them. `pmem_overview` and `pmem_relations` are bounded index/provenance reads, not proof of source freshness or truth.

For a bugfix, reproduce first, then verify the fix and affected contracts. Refresh impact/test recommendations only when the diff warrants it; recommendations do not authorize execution. In a non-Git container, Git impact/tests `unavailable` is not an empty successful diff. Use the shared explicit `--no-git-init` protocol for container installation; never initialize a parent workspace implicitly.

Record only relevant sanitized failure evidence with `./pmem record-failure` when useful, then repair and rerun invalidated checks. For security-sensitive changes, select the relevant secret-safety audit. Inspect large files and logs locally; share only necessary findings, paths, IDs, and short excerpts. Never index, print, or store secrets.
