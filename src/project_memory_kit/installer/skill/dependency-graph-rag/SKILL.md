---
name: dependency-graph-rag
description: Use for the mandatory local project-memory workflow before and after meaningful code changes: dependency impact analysis, context building, coding, bug fixing, refactoring, tests, and failure investigation.
---

# Dependency Graph RAG

Use this repository's local project memory before and after meaningful changes.

## Trigger

Use this skill for:

- feature implementation
- bug fixing
- refactoring
- API changes
- config changes
- migration changes
- schema changes
- routing changes
- auth or security changes
- persistence changes
- test changes
- build or dependency changes
- code review
- architecture analysis
- failure investigation

Skip only typo-only documentation edits that cannot affect runtime behavior.

## Before Editing

Run:

```bash
./pmem doctor
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "<user task>" --base HEAD --out .project-memory/reports/CHANGE_CONTEXT.md
```

Read:

```text
.project-memory/reports/CHANGE_CONTEXT.md
```

Extract:

- target files
- target symbols
- direct dependencies
- reverse dependencies
- affected tests
- related previous failures
- architecture constraints
- low-confidence graph areas

## Editing Rules

- Edit only the files required by the task and impact report.
- Inspect direct callers before changing behavior.
- Inspect reverse imports before changing modules.
- Inspect descendants before changing base classes.
- Inspect tests before changing tested behavior.
- Preserve public API compatibility unless the task requires an API change.
- Mark uncertainty in the final response when graph confidence is low.
- Never store secrets in memory.

## After Editing

Run:

```bash
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem tests --base HEAD
```

Run the returned targeted test commands.

If a test fails:

```bash
mkdir -p .project-memory/logs
./pmem record-failure --command "<command>" --log-file "<log path>"
./pmem context --task "fix failing tests after current change" --base HEAD --out .project-memory/reports/CHANGE_CONTEXT.md
```

Then repair and repeat:

```bash
./pmem index --mode changed
./pmem tests --base HEAD
```

## Final Answer

Report:

- files changed
- symbols changed
- dependencies checked
- tests run
- failure memory updates
- remaining risk
