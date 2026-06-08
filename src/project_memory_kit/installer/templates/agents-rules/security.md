# Security Rules

Do not read, print, index, summarize, or store secrets unless the user explicitly asks for a secret-handling task.

Before commits that touch config, auth, integrations, environment handling, or credentials, run:

```bash
./pmem audit --secrets
```

Report only paths, rule names, and fingerprints. Never include secret values in chat, logs, memory, or Git.
