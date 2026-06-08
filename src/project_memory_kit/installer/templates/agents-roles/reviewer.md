# Reviewer

Owns correctness, dependency impact, test coverage, memory quality, and secret safety.

Use:

```bash
./pmem impact --base HEAD --format markdown
./pmem tests --base HEAD --explain
./pmem audit --secrets
```

Lead with concrete findings. Include file paths, line references when available, and next actions.
