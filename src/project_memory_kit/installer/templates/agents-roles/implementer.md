# Implementer

Owns scoped code changes.

Before editing:

```bash
./pmem context --task "<task>" --base HEAD --reset-task --out .project-memory/reports/CHANGE_CONTEXT.md
./pmem impact --base HEAD --format markdown
```

After editing:

```bash
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem tests --base HEAD --explain
```

If a test fails, store the failure with `./pmem record-failure` and continue from updated context.
