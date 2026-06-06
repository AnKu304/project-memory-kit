## Local Project Memory Protocol

This repository uses local Dependency Graph RAG project memory.

The memory system is installed in:

```text
.project-memory/
tools/project_memory/
.agents/skills/dependency-graph-rag/
```

Before any meaningful code, config, schema, dependency, API, test, build, routing, migration, auth, persistence, or architecture change, run:

```bash
./pmem doctor
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "<current task>" --base HEAD --out .project-memory/reports/CHANGE_CONTEXT.md
```

Read `.project-memory/reports/CHANGE_CONTEXT.md` before editing. Identify target files, target symbols, direct dependencies, reverse dependencies, affected tests, related previous failures, architecture constraints, and low-confidence graph areas.

After editing, run:

```bash
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem tests --base HEAD
```

Run the targeted test commands returned by `./pmem tests`.

If a test fails:

```bash
mkdir -p .project-memory/logs
./pmem record-failure --command "<failed command>" --log-file "<log path>"
./pmem context --task "fix failing tests after current change" --base HEAD --out .project-memory/reports/CHANGE_CONTEXT.md
```

Final responses after code changes must include files changed, symbols changed, impact checked, tests run, failure memory updates, and remaining risk.

External skills may also exist in `.agents/skills/`. Use them when relevant, but they do not replace this mandatory project-memory protocol.

Never index, print, or store secrets.

