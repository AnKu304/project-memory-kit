---
name: dependency-graph-rag
description: Use for the mandatory local project-memory workflow before and after meaningful code or knowledge work: dependency impact analysis, knowledge context, coding, bug fixing, refactoring, tests, research, architecture, SEO, design, UX, product principles, and failure investigation.
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
- research or resource analysis
- SEO, UX, design, product, or content principles
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

For research, product, UX, design, SEO, architecture, content, positioning, or principle-heavy work, also run:

```bash
./pmem knowledge context --task "<user task>" --out .project-memory/reports/KNOWLEDGE_CONTEXT.md
```

Read the retrieved full Markdown files before relying on a rule or research note.

Keep context bounded. Use `pmem` reports, targeted search, local tests, and concise summaries first. Do not paste large files or logs into the chat unless local reports are insufficient or the failure is ambiguous.

Extract:

- target files
- target symbols
- direct dependencies
- reverse dependencies
- affected tests
- related previous failures
- architecture constraints
- current project knowledge
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
- Use only `current` knowledge by default.
- Update changed principles with `./pmem knowledge update`; do not create duplicate current rules.
- Prefer local verification and small summaries over sending raw large outputs to the model.

## After Editing

Run:

```bash
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem tests --base HEAD
```

Run the returned targeted test commands.

Use local project tooling and temporary sandboxes for verification when available. Save long failure logs under `.project-memory/logs/` and record them with `./pmem record-failure`; summarize only the relevant result.

If durable research, architecture, SEO, design, UX, product, or content context changed:

```bash
./pmem knowledge add --type "<type>" --title "<title>" --file "<markdown file>"
./pmem knowledge update --id "<knowledge id>" --file "<markdown file>"
```

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
- knowledge records read or updated
- failure memory updates
- remaining risk
