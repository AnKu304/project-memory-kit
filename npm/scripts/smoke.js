#!/usr/bin/env node

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const root = path.resolve(__dirname, "..", "..");
const wrapper = path.join(root, "npm", "bin", "pmem.js");
const pkg = require(path.join(root, "package.json"));

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd || root,
    encoding: "utf8",
    env: process.env,
    stdio: options.stdio || "pipe"
  });
  if (result.error || result.status !== 0) {
    const output = [result.stdout, result.stderr].filter(Boolean).join("\n");
    throw new Error(`${command} ${args.join(" ")} failed\n${output}`);
  }
  return result;
}

function assertFile(filePath) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`missing expected file: ${filePath}`);
  }
}

const version = run("node", [wrapper, "version"]);
if (version.stdout.trim() !== pkg.version) {
  throw new Error(`version mismatch: ${version.stdout.trim()} !== ${pkg.version}`);
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "pmem-npm-smoke-"));
try {
  run("node", [wrapper, "init", "--target", tmp, "--agent", "multiagent"]);
  assertFile(path.join(tmp, "pmem"));
  assertFile(path.join(tmp, "AGENTS.md"));
  assertFile(path.join(tmp, "CLAUDE.md"));
  assertFile(path.join(tmp, ".agents", "tasks", "_templates", "user-task.md"));
  assertFile(path.join(tmp, ".claude", "settings.json"));

  const installed = run(path.join(tmp, "pmem"), ["version"], { cwd: tmp });
  if (installed.stdout.trim() !== pkg.version) {
    throw new Error(`installed version mismatch: ${installed.stdout.trim()} !== ${pkg.version}`);
  }

  const tasks = run(path.join(tmp, "pmem"), ["tasks", "check"], { cwd: tmp });
  if (!tasks.stdout.includes("Tasks: none")) {
    throw new Error(`unexpected task output:\n${tasks.stdout}`);
  }
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}

console.log(`npm smoke ok: ${pkg.version}`);
