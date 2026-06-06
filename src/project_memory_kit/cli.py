from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from project_memory_kit.installer.install_project import install_project, uninstall_project

try:  # Typer is the packaged CLI. argparse keeps source-tree smoke tests zero-dependency.
    import typer
except Exception:  # pragma: no cover - exercised only when Typer is absent
    typer = None


def _target(value: str | Path | None) -> Path:
    return Path(value or ".").resolve()


def _runtime_args(command: str, args: Iterable[str] = ()) -> int:
    root = Path.cwd()
    runtime_cli = root / "tools" / "project_memory" / "cli.py"
    if not runtime_cli.exists():
        print(
            "Project memory runtime is not installed here. "
            "Run `pmem init` in the repository root first.",
            file=sys.stderr,
        )
        return 2
    cmd = [sys.executable, "-m", "tools.project_memory.cli", command, *args]
    return subprocess.run(cmd, cwd=root).returncode


def init_command(
    target: str = ".",
    agent: str = "codex",
    profile: str = "python",
    runtime: str = "local",
    index: bool = False,
) -> None:
    result = install_project(
        target=_target(target),
        agent=agent,
        profile=profile,
        runtime=runtime,
        run_index=index,
    )
    print(result.summary())


def install_command(
    target: str = ".",
    agent: str = "codex",
    profile: str = "python",
    runtime: str = "local",
    index: bool = False,
) -> None:
    init_command(target=target, agent=agent, profile=profile, runtime=runtime, index=index)


def upgrade_command(target: str = ".") -> None:
    result = install_project(
        target=_target(target),
        agent="codex",
        profile="python",
        runtime="local",
        run_index=False,
        upgrade=True,
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
        agent: str = typer.Option("codex", "--agent", help="Agent profile."),
        profile: str = typer.Option("python", "--profile", help="Project language profile."),
        runtime: str = typer.Option("local", "--runtime", help="Runtime mode."),
        index: bool = typer.Option(False, "--index", help="Run first full index after install."),
    ) -> None:
        init_command(target=target, agent=agent, profile=profile, runtime=runtime, index=index)

    @app.command("install")
    def install_typer(
        target: str = typer.Option(".", "--target", help="Repository root to install into."),
        agent: str = typer.Option("codex", "--agent", help="Agent profile."),
        profile: str = typer.Option("python", "--profile", help="Project language profile."),
        runtime: str = typer.Option("local", "--runtime", help="Runtime mode."),
        index: bool = typer.Option(False, "--index", help="Run first full index after install."),
    ) -> None:
        install_command(target=target, agent=agent, profile=profile, runtime=runtime, index=index)

    @app.command("upgrade")
    def upgrade_typer(
        target: str = typer.Option(".", "--target", help="Repository root to upgrade."),
    ) -> None:
        upgrade_command(target=target)

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

    for _name in ["doctor", "index", "impact", "context", "tests", "record-failure", "search"]:
        app.command(_name, context_settings={"allow_extra_args": True, "ignore_unknown_options": True})(
            _forward(_name)
        )


def _argparse_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="pmem")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ["init", "install"]:
        p = sub.add_parser(name)
        p.add_argument("--target", default=".")
        p.add_argument("--agent", default="codex")
        p.add_argument("--profile", default="python")
        p.add_argument("--runtime", default="local")
        p.add_argument("--index", action="store_true")

    p = sub.add_parser("upgrade")
    p.add_argument("--target", default=".")

    p = sub.add_parser("uninstall")
    p.add_argument("--target", default=".")
    p.add_argument("--purge", action="store_true")
    p.add_argument("--keep-memory", action="store_true", default=True)

    for name in ["doctor", "index", "impact", "context", "tests", "record-failure", "search"]:
        p = sub.add_parser(name)
        p.add_argument("args", nargs=argparse.REMAINDER)

    ns = parser.parse_args(argv)
    if ns.command in {"init", "install"}:
        init_command(ns.target, ns.agent, ns.profile, ns.runtime, ns.index)
        return 0
    if ns.command == "upgrade":
        upgrade_command(ns.target)
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

