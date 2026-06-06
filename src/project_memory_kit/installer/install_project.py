from __future__ import annotations

import shutil
import subprocess
import sys
import os
from dataclasses import dataclass
from pathlib import Path

from project_memory_kit.installer.agents_md import merge_agents_block, remove_agents_block
from project_memory_kit.installer.copy_runtime import copy_tree
from project_memory_kit.installer.gitignore import merge_gitignore, remove_gitignore_block
from project_memory_kit.installer.manifest import InstallReport, write_managed_file, write_text_file
from project_memory_kit.installer.templates import read_template, runtime_root, skill_root, template_path


@dataclass
class ProjectInstallResult:
    report: InstallReport

    def summary(self) -> str:
        return self.report.summary()


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _ensure_git_repo(root: Path, report: InstallReport) -> None:
    if (root / ".git").exists():
        report.commands.append("git repository detected")
        return
    if shutil.which("git") is None:
        report.commands.append("git not found; repository was not initialized")
        return
    result = _run(["git", "init"], cwd=root)
    if result.returncode == 0:
        report.commands.append("git init")
    else:
        report.commands.append(f"git init failed: {result.stderr.strip()}")


def _write_wrappers(root: Path, report: InstallReport) -> None:
    bash = """#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
export PYTHONDONTWRITEBYTECODE=1
cd "$ROOT"
exec "$PYTHON_BIN" -m tools.project_memory.cli "$@"
"""
    ps1 = """$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$env:PYTHONDONTWRITEBYTECODE = "1"
Set-Location $Root
& $Python -m tools.project_memory.cli @args
exit $LASTEXITCODE
"""
    write_text_file(root / "pmem", bash, report, executable=True)
    write_text_file(root / "pmem.ps1", ps1, report)


def _run_runtime(root: Path, report: InstallReport, args: list[str]) -> None:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "tools.project_memory.cli", *args],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    command = "./pmem " + " ".join(args)
    if result.returncode == 0:
        report.commands.append(command)
    else:
        stderr = result.stderr.strip() or result.stdout.strip()
        report.commands.append(f"{command} failed: {stderr}")


def install_project(
    target: Path,
    agent: str = "codex",
    profile: str = "python",
    runtime: str = "local",
    run_index: bool = False,
    upgrade: bool = False,
) -> ProjectInstallResult:
    root = target.resolve()
    root.mkdir(parents=True, exist_ok=True)
    report = InstallReport(target=root)

    _ensure_git_repo(root, report)

    project_memory = root / ".project-memory"
    project_memory.mkdir(parents=True, exist_ok=True)
    (project_memory / "logs").mkdir(exist_ok=True)
    (project_memory / "reports").mkdir(exist_ok=True)

    config_dest = project_memory / "config.yaml"
    if config_dest.exists() and not upgrade:
        report.add_path("preserved", config_dest)
    else:
        write_managed_file(template_path("project-memory.config.yaml"), config_dest, report)

    write_managed_file(template_path("project-memory.gitignore"), project_memory / ".gitignore", report)
    write_managed_file(template_path("README.project-memory.md"), project_memory / "README.md", report)

    merge_gitignore(root / ".gitignore", read_template("root.gitignore.block"), report)
    merge_agents_block(root / "AGENTS.md", read_template("AGENTS.block.md"), report)

    copy_tree(skill_root(), root / ".agents" / "skills" / "dependency-graph-rag", report)
    copy_tree(runtime_root() / "tools" / "project_memory", root / "tools" / "project_memory", report)
    _write_wrappers(root, report)

    _run_runtime(root, report, ["init"])
    _run_runtime(root, report, ["doctor"])
    if run_index:
        _run_runtime(root, report, ["index", "--mode", "full"])

    report.commands.append(f"agent={agent} profile={profile} runtime={runtime}")
    return ProjectInstallResult(report)


def uninstall_project(target: Path, purge: bool = False, keep_memory: bool = True) -> ProjectInstallResult:
    root = target.resolve()
    report = InstallReport(target=root)
    remove_agents_block(root / "AGENTS.md", report)
    remove_gitignore_block(root / ".gitignore", report)
    for path in [
        root / "pmem",
        root / "pmem.ps1",
        root / ".agents" / "skills" / "dependency-graph-rag",
        root / "tools" / "project_memory",
    ]:
        if path.is_dir():
            shutil.rmtree(path)
            report.add_path("updated", path)
        elif path.exists():
            path.unlink()
            report.add_path("updated", path)
    if purge or not keep_memory:
        state = root / ".project-memory"
        if state.exists():
            shutil.rmtree(state)
            report.add_path("updated", state)
    return ProjectInstallResult(report)
