#!/usr/bin/env node

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const packageRoot = path.resolve(__dirname, "..", "..");

function candidatePythons() {
  if (process.env.PYTHON) {
    return [{ command: process.env.PYTHON, prefix: [] }];
  }
  if (process.platform === "win32") {
    return [
      { command: "py", prefix: ["-3"] },
      { command: "python", prefix: [] },
      { command: "python3", prefix: [] }
    ];
  }
  return [
    { command: "python3", prefix: [] },
    { command: "python", prefix: [] }
  ];
}

function selectPython() {
  for (const item of candidatePythons()) {
    const probe = spawnSync(item.command, [
      ...item.prefix,
      "-c",
      "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    ], {
      stdio: "ignore",
      env: process.env
    });
    if (!probe.error && probe.status === 0) {
      return item;
    }
  }
  return null;
}

const python = selectPython();
if (!python) {
  console.error("project-memory-kit requires Python 3.11+ on PATH, or set PYTHON=/path/to/python.");
  process.exit(2);
}

const srcPath = path.join(packageRoot, "src");
const existingPythonPath = process.env.PYTHONPATH || "";
const env = {
  ...process.env,
  PYTHONDONTWRITEBYTECODE: "1",
  PYTHONPATH: existingPythonPath ? `${srcPath}${path.delimiter}${existingPythonPath}` : srcPath
};

const child = spawnSync(
  python.command,
  [...python.prefix, "-m", "project_memory_kit.cli", ...process.argv.slice(2)],
  {
    cwd: process.cwd(),
    env,
    stdio: "inherit"
  }
);

if (child.error) {
  console.error(child.error.message);
  process.exit(2);
}

process.exit(child.status === null ? 1 : child.status);
