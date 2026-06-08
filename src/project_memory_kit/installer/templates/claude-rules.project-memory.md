# Project Memory Rules

Use project memory before meaningful code, config, schema, dependency, API, test, build, routing, migration, auth, persistence, or architecture changes.

## Standard Start

```bash
./pmem doctor
./pmem status
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "<current task>" --base HEAD --reset-task --out .project-memory/reports/CHANGE_CONTEXT.md
```

Read the generated report before editing. Identify target files, target symbols, direct dependencies, reverse dependencies, affected tests, previous failures, project principles, and low-confidence graph areas.

## Research And Principles

For product, UX, design, SEO, architecture, content, positioning, policy, or resource-behavior research:

```bash
./pmem knowledge context --task "<current task>" --out .project-memory/reports/KNOWLEDGE_CONTEXT.md
```

Open full Markdown records only when the short context is not enough.

When a durable principle changes:

```bash
./pmem knowledge add --type "<research|architecture|seo|design|ux|product|decision>" --title "<title>" --file "<markdown file>"
./pmem knowledge update --id "<knowledge id>" --file "<markdown file>"
./pmem knowledge retire --id "<knowledge id>"
```

Use `knowledge update` for changed principles. Do not keep competing `current` records for the same rule.

## Rationale

For "why", rejected approaches, previous failures, experiments, invariants, and architecture/tool/storage choices:

```bash
./pmem rationale context --task "<current task>" --out .project-memory/reports/RATIONALE_CONTEXT.md
```

When a durable cause or decision changes:

```bash
./pmem rationale add --type "<decision|rejection|experiment|constraint>" --title "<title>" --file "<markdown file>"
./pmem rationale update --id "<rationale id>" --file "<markdown file>"
./pmem rationale retire --id "<rationale id>"
```

Rationale records should point to facts such as tests, logs, diffs, files, failures, or commits.

## Verification

After edits:

```bash
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem tests --base HEAD --explain
```

Run the targeted test commands returned by `./pmem tests --base HEAD`.

When a test fails:

```bash
mkdir -p .project-memory/logs
./pmem record-failure --command "<failed command>" --log-file "<log path>"
./pmem context --task "fix failing tests after current change" --base HEAD --out .project-memory/reports/CHANGE_CONTEXT.md
```

## Context Hygiene

Use local tools to inspect large files, logs, reports, and test output. Summarize only the relevant result in the working context. Open full files or long logs only when local summaries are not enough.

Before committing security-sensitive changes:

```bash
./pmem audit --secrets
```

Never index, print, or store secrets.
