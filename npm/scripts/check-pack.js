#!/usr/bin/env node

const path = require("node:path");
const { spawnSync } = require("node:child_process");

const root = path.resolve(__dirname, "..", "..");
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";

function fail(message) {
  console.error(message);
  process.exit(1);
}

const result = spawnSync(npmCommand, ["pack", "--dry-run", "--json", "--ignore-scripts"], {
  cwd: root,
  encoding: "utf8",
  stdio: "pipe"
});

if (result.error || result.status !== 0) {
  fail(`npm pack failed\n${result.stdout || ""}\n${result.stderr || ""}`);
}

let pack;
try {
  pack = JSON.parse(result.stdout)[0];
} catch (error) {
  fail(`could not parse npm pack output: ${error.message}\n${result.stdout}`);
}

const files = new Set(pack.files.map((item) => item.path));
const required = [
  "package.json",
  "pyproject.toml",
  "README.md",
  "README.en.md",
  "CHANGELOG.md",
  "LICENSE",
  "docs/npm.md",
  "npm/bin/pmem.js",
  "npm/scripts/smoke.js",
  "npm/scripts/check-pack.js",
  "src/project_memory_kit/cli.py",
  "src/project_memory_kit/installer/templates/AGENTS.block.md",
  "src/project_memory_kit/installer/templates/evals/search.example.jsonl",
  "src/project_memory_kit/installer/runtime/tools/project_memory/cli.py",
  "src/project_memory_kit/installer/runtime/tools/project_memory/graph/schema.sql"
];

const missing = required.filter((item) => !files.has(item));
if (missing.length) {
  fail(`npm package is missing required files:\n${missing.join("\n")}`);
}

const forbidden = [...files].filter((item) => (
  item.includes("__pycache__/") ||
  item.endsWith(".pyc") ||
  item.startsWith("tests/") ||
  item.startsWith(".github/") ||
  item.startsWith("_local-notes/") ||
  item === "TASK.md" ||
  item === ".DS_Store"
));

if (forbidden.length) {
  fail(`npm package contains forbidden files:\n${forbidden.join("\n")}`);
}

console.log(`npm pack check ok: ${pack.name}@${pack.version}, ${pack.entryCount} files`);
