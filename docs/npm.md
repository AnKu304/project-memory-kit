# npm Distribution

The npm package exposes the same `pmem` installer through a Node wrapper. The wrapper does not reimplement project memory; it locates Python 3.11+ and runs the Python CLI from the packaged source.

Install into a project:

```bash
npx --yes @anku/project-memory-kit pmem init --target .
```

Before the package is published to npm, use the GitHub package form:

```bash
npx --yes --package github:AnKu304/project-memory-kit pmem init --target .
```

Local checks before publishing:

```bash
npm test
npm run smoke
npm run pack:check
npm pack --dry-run
```

What the checks verify:

- wrapper runs `pmem version`;
- wrapper installs a multi-agent project into a temp directory;
- installed `pmem` runs from the generated project;
- package tarball includes runtime/templates/docs required for installation;
- package tarball excludes tests, CI files, local notes, `TASK.md`, `__pycache__`, and `.pyc` files.

Publishing still needs an authenticated npm account with access to the `@anku` scope:

```bash
npm publish --access public
```
