from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from project_memory_kit.installer.install_project import install_project, uninstall_project
from project_memory_kit.version import __version__

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

try:  # Typer is the packaged CLI. argparse keeps source-tree smoke tests zero-dependency.
    import typer
except Exception:  # pragma: no cover - exercised only when Typer is absent
    typer = None


def _target(value: str | Path | None) -> Path:
    return Path(value or ".").resolve()


def _run_runtime(root: Path, command: str, args: Iterable[str] = ()) -> subprocess.CompletedProcess[str]:
    runtime_cli = root / "tools" / "project_memory" / "cli.py"
    if not runtime_cli.exists():
        return subprocess.CompletedProcess([command, *args], 2, "", "Project memory runtime is not installed here.")
    cmd = [sys.executable, "-m", "tools.project_memory.cli", command, *args]
    return subprocess.run(cmd, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _runtime_args(command: str, args: Iterable[str] = ()) -> int:
    result = _run_runtime(Path.cwd(), command, args)
    if result.returncode == 2 and result.stderr == "Project memory runtime is not installed here.":
        print(
            "Project memory runtime is not installed here. "
            "Run `pmem init` in the repository root first.",
            file=sys.stderr,
        )
    else:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
    return result.returncode


@dataclass(frozen=True)
class WizardChoices:
    agent: str
    enable_human: bool
    vector_backend: str
    with_vector: bool
    write_mcp: bool


def _prompt_choice(input_func: Callable[[str], str], label: str, choices: list[str], default: str) -> str:
    raw = input_func(f"{label} ({'/'.join(choices)}) [{default}]: ").strip().lower()
    value = raw or default
    return value if value in choices else default


def _prompt_bool(input_func: Callable[[str], str], label: str, default: bool = False) -> bool:
    suffix = "Y/n" if default else "y/N"
    raw = input_func(f"{label} [{suffix}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"1", "y", "yes", "true", "on"}


def _interactive_choices(input_func: Callable[[str], str] = input) -> WizardChoices:
    agent = _prompt_choice(input_func, "Agent profile", ["codex", "claude", "multiagent"], "codex")
    task_templates = _prompt_bool(input_func, "Install multi-agent task templates", False)
    if task_templates and agent != "multiagent":
        print("Task templates use the multiagent profile; switching agent profile to multiagent.")
        agent = "multiagent"
    enable_human = _prompt_bool(input_func, "Enable Human layer", False)
    vector = _prompt_choice(input_func, "Vector backend", ["auto", "fallback", "qdrant", "managed"], "auto")
    write_mcp = _prompt_bool(input_func, "Write MCP config", False)
    return WizardChoices(
        agent=agent,
        enable_human=enable_human,
        vector_backend="auto" if vector == "managed" else vector,
        with_vector=vector == "managed",
        write_mcp=write_mcp,
    )


def _set_vector_backend(root: Path, backend: str) -> None:
    if backend == "auto":
        return
    path = root / ".project-memory" / "config.yaml"
    if yaml is None:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        pattern = r"(?ms)(^vector:\s*\n(?:^[ \t]+(?!backend:).*\n)*?^[ \t]+backend:\s*)(\S+)"
        if re.search(pattern, text):
            text = re.sub(pattern, rf"\g<1>{backend}", text, count=1)
        else:
            text = text.rstrip() + f"\nvector:\n  backend: {backend}\n"
        path.write_text(text, encoding="utf-8")
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.setdefault("vector", {})["backend"] = backend
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _run_post_install(root: Path, choices: WizardChoices) -> None:
    _set_vector_backend(root, choices.vector_backend)
    if choices.enable_human:
        result = _run_runtime(root, "modules", ["set", "human", "--enabled", "true"])
        if result.returncode != 0:
            print(result.stderr or result.stdout, file=sys.stderr)
    if choices.write_mcp:
        client = "claude" if choices.agent == "claude" else "codex"
        result = _run_runtime(root, "mcp-config", ["--client", client, "--write"])
        if result.returncode == 0 and result.stdout:
            print(result.stdout, end="")
        elif result.returncode != 0:
            print(result.stderr or result.stdout, file=sys.stderr)


def init_command(
    target: str = ".",
    agent: str = "codex",
    profile: str = "python",
    runtime: str = "local",
    index: bool = False,
    with_vector: bool = False,
    interactive: bool = False,
    input_func: Callable[[str], str] = input,
) -> None:
    choices: WizardChoices | None = None
    if interactive:
        choices = _interactive_choices(input_func)
        agent = choices.agent
        with_vector = with_vector or choices.with_vector
    root = _target(target)
    result = install_project(
        target=root,
        agent=agent,
        profile=profile,
        runtime=runtime,
        run_index=index,
        with_vector=with_vector,
    )
    if choices:
        _run_post_install(root, choices)
    print(result.summary())


def install_command(
    target: str = ".",
    agent: str = "codex",
    profile: str = "python",
    runtime: str = "local",
    index: bool = False,
    with_vector: bool = False,
    interactive: bool = False,
) -> None:
    init_command(
        target=target,
        agent=agent,
        profile=profile,
        runtime=runtime,
        index=index,
        with_vector=with_vector,
        interactive=interactive,
    )


def upgrade_command(target: str = ".", agent: str = "auto", with_vector: bool = False) -> None:
    result = install_project(
        target=_target(target),
        agent=agent,
        profile="python",
        runtime="local",
        run_index=False,
        upgrade=True,
        with_vector=with_vector,
    )
    print(result.summary())


def uninstall_command(target: str = ".", purge: bool = False, keep_memory: bool = True) -> None:
    result = uninstall_project(target=_target(target), purge=purge, keep_memory=keep_memory)
    print(result.summary())


if typer is not None:
    app = typer.Typer(help="Install and run local Dependency Graph RAG project memory.")

    @app.command("init")
    def init_typer(
        target: str = typer.Option(".", "--target", help="Repository root to install into."),
        agent: str = typer.Option("codex", "--agent", help="Agent profile: codex, claude, or multiagent."),
        profile: str = typer.Option("python", "--profile", help="Project language profile."),
        runtime: str = typer.Option("local", "--runtime", help="Runtime mode."),
        index: bool = typer.Option(False, "--index", help="Run first full index after install."),
        with_vector: bool = typer.Option(False, "--with-vector", help="Create a managed runtime venv with Qdrant/FastEmbed."),
        interactive: bool = typer.Option(False, "--interactive", help="Ask for profile and optional features."),
    ) -> None:
        init_command(
            target=target,
            agent=agent,
            profile=profile,
            runtime=runtime,
            index=index,
            with_vector=with_vector,
            interactive=interactive,
        )

    @app.command("install")
    def install_typer(
        target: str = typer.Option(".", "--target", help="Repository root to install into."),
        agent: str = typer.Option("codex", "--agent", help="Agent profile: codex, claude, or multiagent."),
        profile: str = typer.Option("python", "--profile", help="Project language profile."),
        runtime: str = typer.Option("local", "--runtime", help="Runtime mode."),
        index: bool = typer.Option(False, "--index", help="Run first full index after install."),
        with_vector: bool = typer.Option(False, "--with-vector", help="Create a managed runtime venv with Qdrant/FastEmbed."),
        interactive: bool = typer.Option(False, "--interactive", help="Ask for profile and optional features."),
    ) -> None:
        install_command(
            target=target,
            agent=agent,
            profile=profile,
            runtime=runtime,
            index=index,
            with_vector=with_vector,
            interactive=interactive,
        )

    @app.command("upgrade")
    def upgrade_typer(
        target: str = typer.Option(".", "--target", help="Repository root to upgrade."),
        agent: str = typer.Option("auto", "--agent", help="Agent profile to preserve or install: auto, codex, claude, or multiagent."),
        with_vector: bool = typer.Option(False, "--with-vector", help="Create or update the managed vector runtime venv."),
    ) -> None:
        upgrade_command(target=target, agent=agent, with_vector=with_vector)

    @app.command("version")
    def version_typer() -> None:
        print(__version__)

    @app.command("uninstall")
    def uninstall_typer(
        target: str = typer.Option(".", "--target", help="Repository root."),
        purge: bool = typer.Option(False, "--purge", help="Remove memory state too."),
        keep_memory: bool = typer.Option(True, "--keep-memory/--no-keep-memory"),
    ) -> None:
        uninstall_command(target=target, purge=purge, keep_memory=keep_memory)

    def _forward(name: str):
        def handler(ctx: typer.Context) -> None:
            code = _runtime_args(name, ctx.args)
            raise typer.Exit(code)

        return handler

    for _name in [
        "doctor",
        "status",
        "index",
        "impact",
        "context",
        "tests",
        "record-failure",
        "search",
        "eval",
        "audit",
        "optimize",
        "stale",
        "report",
        "watch",
        "knowledge",
        "rationale",
        "migrate",
        "modules",
        "mcp",
        "mcp-config",
        "tasks",
        "human",
    ]:
        app.command(_name, context_settings={"allow_extra_args": True, "ignore_unknown_options": True})(
            _forward(_name)
        )


def _argparse_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="pmem")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ["init", "install"]:
        p = sub.add_parser(name)
        p.add_argument("--target", default=".")
        p.add_argument("--agent", choices=["codex", "claude", "universal", "multiagent", "all"], default="codex")
        p.add_argument("--profile", default="python")
        p.add_argument("--runtime", default="local")
        p.add_argument("--index", action="store_true")
        p.add_argument("--with-vector", action="store_true")
        p.add_argument("--interactive", action="store_true")

    p = sub.add_parser("upgrade")
    p.add_argument("--target", default=".")
    p.add_argument("--agent", choices=["auto", "preserve", "codex", "claude", "universal", "multiagent", "all"], default="auto")
    p.add_argument("--with-vector", action="store_true")

    p = sub.add_parser("uninstall")
    p.add_argument("--target", default=".")
    p.add_argument("--purge", action="store_true")
    p.add_argument("--keep-memory", action="store_true", default=True)

    sub.add_parser("version")

    for name in [
        "doctor",
        "status",
        "index",
        "impact",
        "context",
        "tests",
        "record-failure",
        "search",
        "eval",
        "audit",
        "optimize",
        "stale",
        "report",
        "watch",
        "knowledge",
        "rationale",
        "migrate",
        "modules",
        "mcp",
        "mcp-config",
        "tasks",
        "human",
    ]:
        p = sub.add_parser(name)
        p.add_argument("args", nargs=argparse.REMAINDER)

    ns = parser.parse_args(argv)
    if ns.command in {"init", "install"}:
        init_command(ns.target, ns.agent, ns.profile, ns.runtime, ns.index, ns.with_vector, ns.interactive)
        return 0
    if ns.command == "upgrade":
        upgrade_command(ns.target, ns.agent, ns.with_vector)
        return 0
    if ns.command == "version":
        print(__version__)
        return 0
    if ns.command == "uninstall":
        uninstall_command(ns.target, ns.purge, ns.keep_memory)
        return 0
    return _runtime_args(ns.command, ns.args)


def main() -> None:
    if typer is not None:
        app()
    else:
        raise SystemExit(_argparse_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
