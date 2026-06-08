from __future__ import annotations

import json
import shutil
import subprocess
import sys
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except Exception:  # pragma: no cover - source-tree fallback
    yaml = None

from project_memory_kit.installer.agents_md import merge_agents_block, remove_agents_block
from project_memory_kit.installer.copy_runtime import copy_tree
from project_memory_kit.installer.gitignore import merge_gitignore, remove_gitignore_block
from project_memory_kit.installer.manifest import InstallReport, timestamp, write_managed_file, write_text_file
from project_memory_kit.installer.templates import read_template, runtime_root, skill_root, template_path
from project_memory_kit.version import CONFIG_SCHEMA_VERSION, GRAPH_SCHEMA_VERSION, __version__


AGENT_PROFILES = {"codex", "claude", "multiagent"}


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
if [[ -n "${PYTHON:-}" ]]; then
  PYTHON_BIN="$PYTHON"
elif [[ -x "$ROOT/.project-memory/runtime/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT/.project-memory/runtime/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi
export PYTHONDONTWRITEBYTECODE=1
cd "$ROOT"
exec "$PYTHON_BIN" -m tools.project_memory.cli "$@"
"""
    ps1 = """$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $Root ".project-memory/runtime/.venv/Scripts/python.exe"
$Python = if ($env:PYTHON) { $env:PYTHON } elseif (Test-Path $VenvPython) { $VenvPython } else { "python" }
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


def _read_install_metadata(root: Path) -> dict[str, object]:
    path = root / ".project-memory" / "install.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _normalize_agent_profile(root: Path, agent: str, upgrade: bool = False) -> str:
    value = (agent or "codex").strip().lower()
    if value in {"all", "universal", "universal-agents", "universal_agents"}:
        value = "multiagent"
    if value in {"auto", "preserve"}:
        previous = _read_install_metadata(root)
        value = str(previous.get("agent_profile") or previous.get("agent") or "codex").strip().lower()
        if value in {"all", "universal", "universal-agents", "universal_agents"}:
            value = "multiagent"
    if value not in AGENT_PROFILES:
        choices = ", ".join(["codex", "claude", "multiagent"])
        raise ValueError(f"unsupported agent profile `{agent}`; choose one of: {choices}")
    if upgrade and value == "codex":
        previous = _read_install_metadata(root)
        previous_profile = str(previous.get("agent_profile") or "").strip().lower()
        if previous_profile in AGENT_PROFILES and previous_profile != "codex" and agent in {"", "auto", "preserve"}:
            return previous_profile
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _deep_fill(existing: dict, defaults: dict) -> dict:
    result = dict(existing)
    for key, value in defaults.items():
        if key not in result:
            result[key] = value
        elif isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_fill(result[key], value)
    return result


def _write_or_merge_config(config_dest: Path, upgrade: bool, report: InstallReport) -> None:
    if not config_dest.exists():
        write_managed_file(template_path("project-memory.config.yaml"), config_dest, report)
        return
    if not upgrade:
        report.add_path("preserved", config_dest)
        return
    if yaml is None:
        report.add_path("preserved", config_dest)
        return

    template = yaml.safe_load(template_path("project-memory.config.yaml").read_text(encoding="utf-8")) or {}
    try:
        current = yaml.safe_load(config_dest.read_text(encoding="utf-8")) or {}
    except Exception:
        backup = config_dest.with_name(f"{config_dest.name}.bak.{timestamp()}")
        shutil.copy2(config_dest, backup)
        report.add_path("backed_up", backup)
        write_managed_file(template_path("project-memory.config.yaml"), config_dest, report)
        return

    merged = _deep_fill(current, template)
    rendered = yaml.safe_dump(merged, allow_unicode=True, sort_keys=False)
    if config_dest.read_text(encoding="utf-8") == rendered:
        report.add_path("preserved", config_dest)
        return
    backup = config_dest.with_name(f"{config_dest.name}.bak.{timestamp()}")
    shutil.copy2(config_dest, backup)
    report.add_path("backed_up", backup)
    config_dest.write_text(rendered, encoding="utf-8")
    report.add_path("updated", config_dest)


def _write_or_merge_claude_settings(path: Path, report: InstallReport) -> None:
    defaults = json.loads(read_template("claude-settings.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        rendered = json.dumps(defaults, indent=2, sort_keys=True) + "\n"
        path.write_text(rendered, encoding="utf-8")
        report.add_path("created", path)
        return
    try:
        current = json.loads(path.read_text(encoding="utf-8")) or {}
    except json.JSONDecodeError:
        backup = path.with_name(f"{path.name}.bak.{timestamp()}")
        shutil.copy2(path, backup)
        report.add_path("backed_up", backup)
        current = {}
    permissions = current.setdefault("permissions", {})
    deny = permissions.setdefault("deny", [])
    if not isinstance(deny, list):
        deny = []
        permissions["deny"] = deny
    changed = False
    for item in defaults.get("permissions", {}).get("deny", []):
        if item not in deny:
            deny.append(item)
            changed = True
    rendered = json.dumps(current, indent=2, sort_keys=True) + "\n"
    if not changed and path.read_text(encoding="utf-8") == rendered:
        report.add_path("preserved", path)
        return
    path.write_text(rendered, encoding="utf-8")
    report.add_path("updated", path)


def _managed_paths_for_profiles(agent_profiles: list[str]) -> list[str]:
    paths = [
        ".project-memory/config.yaml",
        ".project-memory/.gitignore",
        ".project-memory/README.md",
        ".project-memory/install.json",
        "tools/project_memory/",
        "pmem",
        "pmem.ps1",
        ".gitignore",
    ]
    profiles = set(agent_profiles)
    if profiles & {"codex", "multiagent"}:
        paths.extend(["AGENTS.md", ".agents/skills/dependency-graph-rag/"])
    if profiles & {"multiagent"}:
        paths.extend([".agents/roles/", ".agents/tasks/"])
    if profiles & {"claude", "multiagent"}:
        paths.extend(
            [
                "CLAUDE.md",
                ".claude/settings.json",
                ".claude/rules/project-memory.md",
                ".claude/skills/dependency-graph-rag/",
                ".claude/commands/pmem-context.md",
                ".claude/commands/pmem-status.md",
                ".claude/commands/pmem-audit.md",
            ]
        )
    if profiles & {"multiagent"}:
        paths.extend([".claude/agents/"])
    return paths


def _detect_installed_agent_profiles(root: Path, active_profile: str) -> list[str]:
    profiles = {active_profile}
    if (root / "AGENTS.md").exists() or (root / ".agents" / "skills" / "dependency-graph-rag").exists():
        profiles.add("codex")
    if (root / "CLAUDE.md").exists() or (root / ".claude" / "skills" / "dependency-graph-rag").exists():
        profiles.add("claude")
    if (root / ".agents" / "roles").exists() or (root / ".claude" / "agents").exists():
        profiles.add("multiagent")
    if "multiagent" in profiles:
        profiles.update({"codex", "claude"})
    return [item for item in ["codex", "claude", "multiagent"] if item in profiles]


def _write_install_metadata(root: Path, report: InstallReport, operation: str, agent_profile: str) -> None:
    path = root / ".project-memory" / "install.json"
    previous = _read_install_metadata(root)
    now = _utc_now()
    installed_profiles = _detect_installed_agent_profiles(root, agent_profile)
    data = {
        "package": "project-memory-kit",
        "installed_version": __version__,
        "runtime_version": __version__,
        "agent_profile": agent_profile,
        "agent_profiles": installed_profiles,
        "config_schema_version": CONFIG_SCHEMA_VERSION,
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "installed_at": previous.get("installed_at") or now,
        "updated_at": now,
        "previous_version": previous.get("runtime_version"),
        "last_operation": operation,
        "state_preserved": True,
        "managed_paths": _managed_paths_for_profiles(installed_profiles),
        "knowledge_paths": [
            ".project-memory/knowledge/",
        ],
        "rationale_paths": [
            ".project-memory/rationale/",
        ],
        "eval_paths": [
            ".project-memory/evals/",
        ],
        "optional_paths": [
            ".project-memory/human/",
        ],
        "state_paths": [
            ".project-memory/install.json",
            ".project-memory/graph.sqlite",
            ".project-memory/linear/",
            ".project-memory/qdrant/",
            ".project-memory/runtime/",
            ".project-memory/logs/",
            ".project-memory/reports/",
            ".project-memory/cache/",
            ".project-memory/models/",
            ".project-memory/tmp/",
        ],
    }
    rendered = json.dumps(data, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(rendered, encoding="utf-8")
        report.add_path("created", path)
    elif path.read_text(encoding="utf-8") == rendered:
        report.add_path("preserved", path)
    else:
        path.write_text(rendered, encoding="utf-8")
        report.add_path("updated", path)


def _setup_vector_runtime(root: Path, report: InstallReport) -> None:
    venv = root / ".project-memory" / "runtime" / ".venv"
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        result = subprocess.run([sys.executable, "-m", "venv", str(venv)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            report.commands.append(f"python -m venv .project-memory/runtime/.venv failed: {result.stderr.strip()}")
            return
        report.add_path("created", venv)
    result = subprocess.run(
        [str(python), "-m", "pip", "install", "qdrant-client>=1.9", "fastembed>=0.3"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode == 0:
        report.commands.append("installed vector runtime dependencies")
    else:
        report.commands.append(f"vector runtime dependency install failed: {(result.stderr or result.stdout).strip()}")


def _copy_project_memory_skill(root: Path, base_dir: Path, report: InstallReport) -> None:
    copy_tree(skill_root(), base_dir / "skills" / "dependency-graph-rag", report)


def _install_codex_profile(root: Path, report: InstallReport) -> None:
    merge_agents_block(
        root / "AGENTS.md",
        read_template("AGENTS.block.md"),
        report,
        full_template=read_template("AGENTS.full.md"),
    )
    _copy_project_memory_skill(root, root / ".agents", report)
    copy_tree(template_path("agents-rules"), root / ".agents" / "rules", report)


def _install_claude_profile(root: Path, report: InstallReport, include_multiagent: bool = False) -> None:
    merge_agents_block(
        root / "CLAUDE.md",
        read_template("CLAUDE.block.md"),
        report,
        full_template=read_template("CLAUDE.full.md"),
    )
    _write_or_merge_claude_settings(root / ".claude" / "settings.json", report)
    write_managed_file(template_path("claude-rules.project-memory.md"), root / ".claude" / "rules" / "project-memory.md", report)
    copy_tree(template_path("claude-commands"), root / ".claude" / "commands", report)
    _copy_project_memory_skill(root, root / ".claude", report)
    if include_multiagent:
        copy_tree(template_path("claude-agents"), root / ".claude" / "agents", report)


def _install_multiagent_profile(root: Path, report: InstallReport) -> None:
    _install_codex_profile(root, report)
    _install_claude_profile(root, report, include_multiagent=True)
    copy_tree(template_path("agents-roles"), root / ".agents" / "roles", report)
    copy_tree(template_path("agents-tasks"), root / ".agents" / "tasks", report)


def install_project(
    target: Path,
    agent: str = "codex",
    profile: str = "python",
    runtime: str = "local",
    run_index: bool = False,
    upgrade: bool = False,
    with_vector: bool = False,
) -> ProjectInstallResult:
    root = target.resolve()
    root.mkdir(parents=True, exist_ok=True)
    report = InstallReport(target=root)
    agent_profile = _normalize_agent_profile(root, agent, upgrade=upgrade)

    _ensure_git_repo(root, report)

    project_memory = root / ".project-memory"
    project_memory.mkdir(parents=True, exist_ok=True)
    (project_memory / "logs").mkdir(exist_ok=True)
    (project_memory / "reports").mkdir(exist_ok=True)

    _write_or_merge_config(project_memory / "config.yaml", upgrade=upgrade, report=report)

    write_managed_file(template_path("project-memory.gitignore"), project_memory / ".gitignore", report)
    write_managed_file(template_path("README.project-memory.md"), project_memory / "README.md", report)
    copy_tree(template_path("evals"), project_memory / "evals", report)

    merge_gitignore(root / ".gitignore", read_template("root.gitignore.block"), report)
    if agent_profile == "codex":
        _install_codex_profile(root, report)
    elif agent_profile == "claude":
        _install_claude_profile(root, report)
    else:
        _install_multiagent_profile(root, report)

    copy_tree(runtime_root() / "tools" / "project_memory", root / "tools" / "project_memory", report)
    if with_vector:
        _setup_vector_runtime(root, report)
    _write_wrappers(root, report)
    _write_install_metadata(root, report, "upgrade" if upgrade else "install", agent_profile)

    _run_runtime(root, report, ["init"])
    _run_runtime(root, report, ["migrate"])
    _run_runtime(root, report, ["doctor"])
    if run_index:
        _run_runtime(root, report, ["index", "--mode", "full"])

    report.commands.append(f"version={__version__} agent={agent_profile} profile={profile} runtime={runtime}")
    return ProjectInstallResult(report)


def uninstall_project(target: Path, purge: bool = False, keep_memory: bool = True) -> ProjectInstallResult:
    root = target.resolve()
    report = InstallReport(target=root)
    remove_agents_block(root / "AGENTS.md", report)
    remove_agents_block(root / "CLAUDE.md", report)
    remove_gitignore_block(root / ".gitignore", report)
    for path in [
        root / "pmem",
        root / "pmem.ps1",
        root / ".agents" / "skills" / "dependency-graph-rag",
        root / ".agents" / "rules",
        root / ".agents" / "roles",
        root / ".agents" / "tasks" / "_templates",
        root / ".agents" / "tasks" / "README.md",
        root / ".claude" / "rules" / "project-memory.md",
        root / ".claude" / "skills" / "dependency-graph-rag",
        root / ".claude" / "commands" / "pmem-context.md",
        root / ".claude" / "commands" / "pmem-status.md",
        root / ".claude" / "commands" / "pmem-audit.md",
        root / ".claude" / "agents" / "pmem-coordinator.md",
        root / ".claude" / "agents" / "pmem-implementer.md",
        root / ".claude" / "agents" / "pmem-researcher.md",
        root / ".claude" / "agents" / "pmem-reviewer.md",
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
