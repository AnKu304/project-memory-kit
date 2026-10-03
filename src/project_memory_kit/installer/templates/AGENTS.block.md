## Local Project Memory Protocol

Use this project's single configured PMEM root and `.project-memory/`; the
MCP must serve the same root as `./pmem`. Configuration alone is not a live
connection. Never use a neighbour's memory, a legacy Tencent backend, or silently
initialize/index a parent directory. Preserve secrets, private history and user files.

PMEM retains task context, documents, knowledge, rationale and causal evidence.
Configured GitNexus owns code symbols/dependencies; choose an explicitly bound
repository ID for code query/context/impact/detect-changes. Shared runtime and
registry sit above projects; each root retains isolated data and exact-root MCP.
Refresh documents with PMEM, code with GitNexus. Missing/stale code registration
is degraded coverage, not an empty successful graph. Durable code links keep
repository identity and source revision; never copy the code graph into PMEM.

For meaningful work obtain/read one bounded `pmem_context` or `./pmem context`
and inspect relevant sources; reuse a current same-task receipt. `--reset-task`
is for a new task only. Check active handoffs when shared task ownership matters.
Do not duplicate search/impact/tests already sufficient in context. A typo/status
exchange needs no new memory cycle. If unavailable/stale, state the limitation;
empty or lexical fallback output is not proof of absent knowledge or semantic success.

Doctor is for setup/runtime changes/malfunction; status/index for stale or changed
inputs. Refresh indexed changes once before handoff unless already verified current.
Impact/tests selection is conditional on changed coverage needs; checks follow
affected contracts/risk, without an automatic index/impact/tests sequence or full suite.

Save changed durable findings in knowledge and reasons/alternatives in rationale,
using the installed schema and an existing project-relative file. Update existing
rules rather than duplicating current records. Verify saved/completed record ID/version
with show/search; queued/busy is pending. Do not clear live locks or edit SQLite.
No Git commit/push or external sync is required for local persistence.

Detailed commands and safeguards are an optional task-specific reference:
[PMEM operations](.agents/skills/dependency-graph-rag/references/project-memory-protocol.md).
Read the relevant section for installation, retrieval, writes/locks, failures or
human views; this link is not a command to read/run everything. Project forks
selected by the local contract remain authoritative for their workflow.
