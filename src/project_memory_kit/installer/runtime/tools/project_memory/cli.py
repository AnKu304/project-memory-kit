from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from tools.project_memory.services.context_compiler import write_compiled_context
from tools.project_memory.services.context_builder import write_context
from tools.project_memory.services.doctor import doctor as doctor_service
from tools.project_memory.services.eval_runner import format_eval, run_eval
from tools.project_memory.services.failure_memory import record_failure
from tools.project_memory.services.governance import audit_project, format_audit
from tools.project_memory.services.human import (
    export_human,
    format_human_export,
    format_human_graph,
    format_human_graph_html,
    format_human_search,
    format_human_status,
    format_human_sync,
    human_graph,
    human_graph_html,
    human_status,
    search_human,
    sync_human,
)
from tools.project_memory.services.impact_analysis import analyze_impact, format_impact
from tools.project_memory.services.index_project import index_project
from tools.project_memory.services.init_memory import init_memory
from tools.project_memory.services.migrations import apply_migrations
from tools.project_memory.services.maintenance import format_optimization, optimize_project
from tools.project_memory.services.memory_report import build_memory_report, format_memory_report
from tools.project_memory.services.mcp_config import build_mcp_config, format_mcp_config, write_mcp_config
from tools.project_memory.mcp import serve_stdio
from tools.project_memory.memory_cli import add_memory_parsers, prepare_memory_arguments
from tools.project_memory.parser_sections import (
    add_concurrency_parsers,
    add_human_parser,
    add_modules_parser,
    add_tasks_parser,
)
from tools.project_memory.services.concurrency import command_lock, command_queue, run_with_write_lock
from tools.project_memory.services.modules import format_module_states, set_module_enabled
from tools.project_memory.services.search import format_search_result, search as search_service
from tools.project_memory.services.status import format_stale, format_status, project_status
from tools.project_memory.services.tasks import close_task, format_tasks, list_tasks
from tools.project_memory.services.tasks_linear import (
    export_linear_tasks,
    format_linear_report,
    format_linear_status,
    import_linear_tasks,
    linear_status,
)
from tools.project_memory.services.auto_index import ensure_fresh_index
from tools.project_memory.services.test_selector import explain_tests, select_tests
from tools.project_memory.version import __version__


def root() -> Path:
    return Path.cwd().resolve()


def command_init(_: argparse.Namespace) -> int:
    print(init_memory(root()))
    return 0


def command_doctor(_: argparse.Namespace) -> int:
    ok, report = doctor_service(root())
    print(report)
    return 0 if ok else 1


def command_status(args: argparse.Namespace) -> int:
    print(format_status(project_status(root()), args.format), end="")
    return 0



def command_index(args: argparse.Namespace) -> int:
    print(index_project(root(), mode=args.mode))
    return 0


def command_impact(args: argparse.Namespace) -> int:
    report = analyze_impact(root(), base=args.base)
    print(format_impact(report, args.format), end="")
    return 0


def command_context(args: argparse.Namespace) -> int:
    out = Path(args.out)
    if not out.is_absolute():
        out = root() / out
    writer = write_compiled_context if args.compiled else write_context
    written = writer(root(), args.task, args.base, out, reset_task=args.reset_task)
    print(written)
    return 0


def command_tests(args: argparse.Namespace) -> int:
    if args.explain:
        print(explain_tests(root(), args.base), end="")
        return 0
    commands = select_tests(root(), args.base)
    for diagnostic in getattr(commands, "diagnostics", []):
        print(f"Warning: {diagnostic}")
    for command in commands:
        print(command)
    return 0


def command_record_failure(args: argparse.Namespace) -> int:
    log_file = Path(args.log_file)
    if not log_file.is_absolute():
        log_file = root() / log_file
    fingerprint = record_failure(root(), args.command, log_file)
    print(fingerprint)
    return 0


def command_search(args: argparse.Namespace) -> int:
    rows = search_service(root(), args.query, args.limit, layer=args.layer, debug=args.debug,
                          audience=getattr(args, "audience", "project"), domain=getattr(args, "domain", None),
                          memory_type=getattr(args, "memory_type", None))
    for diagnostic in getattr(rows, "diagnostics", []):
        print(f"Warning: {diagnostic}")
    for item in rows:
        print(format_search_result(item, debug=args.debug))
    return 0


def command_eval(args: argparse.Namespace) -> int:
    file_path = Path(args.file).resolve() if args.file else None
    report = run_eval(root(), file_path=file_path, limit=args.limit)
    print(format_eval(report, args.format), end="")
    return 0 if int(report["failed"]) == 0 else 1


def command_audit(args: argparse.Namespace) -> int:
    report = audit_project(root(), include_secrets=args.secrets)
    print(format_audit(report, args.format), end="")
    return 0 if report["ok"] else 1


def command_optimize(args: argparse.Namespace) -> int:
    print(format_optimization(optimize_project(root(), vacuum=args.vacuum), args.format), end="")
    return 0


def command_stale(args: argparse.Namespace) -> int:
    print(format_stale(root(), args.format), end="")
    return 0


def command_report(args: argparse.Namespace) -> int:
    print(format_memory_report(build_memory_report(root()), args.format), end="")
    return 0


def command_watch(args: argparse.Namespace) -> int:
    if args.once:
        runs = 1
    elif args.max_runs is not None:
        runs = args.max_runs
    else:
        runs = None if args.serve else 1
    interval = max(float(args.interval), 0.1)
    count = 0
    if args.serve:
        limit = "unbounded" if runs is None else str(runs)
        print(f"watch serve: interval={interval:g} max_runs={limit}")
    try:
        while runs is None or count < runs:
            report = ensure_fresh_index(root(), "watch")
            label = f"watch check {count + 1}"
            if report:
                print(f"{label}: indexed")
                print(report)
            else:
                print(f"{label}: fresh")
            count += 1
            if runs is not None and count >= runs:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("watch serve: stopped")
    return 0


def command_migrate(_: argparse.Namespace) -> int:
    applied = apply_migrations(root())
    if applied:
        print("applied migrations:")
        for item in applied:
            print(f"- {item}")
    else:
        print("migrations up to date")
    return 0


def command_modules(args: argparse.Namespace) -> int:
    try:
        if args.modules_command == "list":
            print(format_module_states(root()))
            return 0
        if args.modules_command == "set":
            enabled = str(args.enabled).strip().lower() in {"1", "true", "yes", "on", "enabled"}
            disabled = str(args.enabled).strip().lower() in {"0", "false", "no", "off", "disabled"}
            if not enabled and not disabled:
                print("--enabled must be true or false", file=sys.stderr)
                return 2
            state = set_module_enabled(root(), args.name, enabled)
            status = "enabled" if state.enabled else "disabled"
            print(f"{state.name}: {status}")
            return 0
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("missing modules command", file=sys.stderr)
    return 2


def command_mcp(args: argparse.Namespace) -> int:
    mcp_root = Path(args.root)
    if not mcp_root.is_absolute():
        mcp_root = root() / mcp_root
    return serve_stdio(mcp_root)


def command_mcp_config(args: argparse.Namespace) -> int:
    mcp_root = Path(args.root)
    if not mcp_root.is_absolute():
        mcp_root = root() / mcp_root
    if args.write:
        path = write_mcp_config(mcp_root, client=args.client)
        print(f"wrote {path}")
        return 0
    print(format_mcp_config(build_mcp_config(mcp_root, client=args.client), args.format), end="")
    return 0


def command_tasks(args: argparse.Namespace) -> int:
    try:
        if args.tasks_command in {"list", "check"}:
            tasks = list_tasks(root(), include_closed=args.all, role=args.role)
            print(format_tasks(tasks), end="")
            return 0
        if args.tasks_command == "close":
            item = close_task(root(), args.file, args.summary, command=args.command)
            print(f"task closed: {item.path}")
            return 0
        if args.tasks_command == "linear":
            if args.linear_command == "status":
                print(format_linear_status(linear_status(root())), end="")
                return 0
            if args.linear_command == "export":
                print(format_linear_report("export", export_linear_tasks(root(), out=args.out)), end="")
                return 0
            if args.linear_command == "import":
                print(format_linear_report("import", import_linear_tasks(root(), args.file)), end="")
                return 0
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("missing tasks command", file=sys.stderr)
    return 2


def command_human(args: argparse.Namespace) -> int:
    try:
        if args.human_command == "status":
            print(format_human_status(human_status(root())), end="")
            return 0
        if args.human_command == "export":
            print(format_human_export(export_human(root())), end="")
            return 0
        if args.human_command == "sync":
            report = sync_human(root())
            print(format_human_sync(report), end="")
            return 1 if report.conflicts else 0
        if args.human_command == "graph":
            if args.html:
                print(format_human_graph_html(human_graph_html(root())), end="")
                return 0
            print(format_human_graph(human_graph(root())), end="")
            return 0
        if args.human_command == "search":
            print(format_human_search(search_human(root(), args.query, args.limit)), end="")
            return 0
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("missing human command", file=sys.stderr)
    return 2


def command_version(_: argparse.Namespace) -> int:
    print(__version__)
    return 0


def command_upgrade(_: argparse.Namespace) -> int:
    print("Upgrade is installer-managed. Run the latest `pipx run --spec <repo> pmem upgrade --target .`.")
    return 0


def command_uninstall(args: argparse.Namespace) -> int:
    print(
        "Uninstall is installer-managed. Re-run `pipx run --spec <repo> pmem uninstall` "
        f"with {'--purge' if args.purge else '--keep-memory'}."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pmem")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init")
    p.set_defaults(func=command_init)

    p = sub.add_parser("doctor")
    p.set_defaults(func=command_doctor)

    p = sub.add_parser("status")
    p.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p.set_defaults(func=command_status)

    add_memory_parsers(sub, lambda: root())

    p = sub.add_parser("index")
    p.add_argument("--mode", choices=["full", "changed"], default="changed")
    p.set_defaults(func=command_index)

    p = sub.add_parser("impact")
    p.add_argument("--base", default="HEAD")
    p.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p.set_defaults(func=command_impact)

    p = sub.add_parser("context")
    p.add_argument("--task", required=True)
    p.add_argument("--base", default="HEAD")
    p.add_argument("--out", default=".project-memory/reports/CHANGE_CONTEXT.md")
    p.add_argument("--reset-task", action="store_true")
    p.add_argument("--compiled", action="store_true")
    p.set_defaults(func=command_context)

    p = sub.add_parser("tests")
    p.add_argument("--base", default="HEAD")
    p.add_argument("--explain", action="store_true")
    p.set_defaults(func=command_tests)

    p = sub.add_parser("record-failure")
    p.add_argument("--command", required=True)
    p.add_argument("--log-file", required=True)
    p.set_defaults(func=command_record_failure)

    p = sub.add_parser("search")
    p.add_argument("--query", required=True)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--layer", choices=["knowledge", "rationale", "human"], default=None)
    p.add_argument("--audience", choices=["project", "agent_tooling", "all"], default="project")
    p.add_argument("--domain", default=None)
    p.add_argument("--type", dest="memory_type", choices=["code", "knowledge", "rationale", "agent_tooling", "document"], default=None)
    p.add_argument("--debug", action="store_true")
    p.set_defaults(func=command_search)

    p = sub.add_parser("eval")
    p.add_argument("--file")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p.set_defaults(func=command_eval)

    p = sub.add_parser("audit")
    p.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p.add_argument("--secrets", action="store_true")
    p.set_defaults(func=command_audit)

    p = sub.add_parser("optimize")
    p.add_argument("--vacuum", action="store_true")
    p.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p.set_defaults(func=command_optimize)

    p = sub.add_parser("stale")
    p.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p.set_defaults(func=command_stale)

    p = sub.add_parser("report")
    p.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p.set_defaults(func=command_report)

    p = sub.add_parser("watch")
    p.add_argument("--once", action="store_true")
    p.add_argument("--serve", action="store_true")
    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--max-runs", type=int)
    p.set_defaults(func=command_watch)

    p = sub.add_parser("migrate")
    p.set_defaults(func=command_migrate)

    add_modules_parser(sub, command_modules)
    add_concurrency_parsers(sub, command_lock, command_queue)

    p = sub.add_parser("mcp")
    p.add_argument("--root", default=".")
    p.set_defaults(func=command_mcp)

    p = sub.add_parser("mcp-config")
    p.add_argument("--root", default=".")
    p.add_argument("--client", choices=["generic", "claude", "codex"], default="generic")
    p.add_argument("--format", choices=["toml", "json"], default="toml")
    p.add_argument("--write", action="store_true")
    p.set_defaults(func=command_mcp_config)

    add_tasks_parser(sub, command_tasks)
    add_human_parser(sub, command_human)

    p = sub.add_parser("version")
    p.set_defaults(func=command_version)

    p = sub.add_parser("upgrade")
    p.set_defaults(func=command_upgrade)

    p = sub.add_parser("uninstall")
    p.add_argument("--purge", action="store_true")
    p.add_argument("--keep-memory", action="store_true", default=True)
    p.set_defaults(func=command_uninstall)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        prepare_memory_arguments(root(), args)
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return run_with_write_lock(root(), args, argv, lambda: int(args.func(args)))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
