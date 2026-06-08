from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from tools.project_memory.services.context_builder import write_context
from tools.project_memory.services.doctor import doctor as doctor_service
from tools.project_memory.services.eval_runner import format_eval, run_eval
from tools.project_memory.services.failure_memory import record_failure
from tools.project_memory.services.governance import audit_project, format_audit
from tools.project_memory.services.human import (
    export_human,
    format_human_export,
    format_human_graph,
    format_human_search,
    format_human_status,
    format_human_sync,
    human_graph,
    human_status,
    search_human,
    sync_human,
)
from tools.project_memory.services.impact_analysis import analyze_impact, format_impact
from tools.project_memory.services.index_project import index_project
from tools.project_memory.services.init_memory import init_memory
from tools.project_memory.services.knowledge import (
    add_knowledge,
    build_knowledge_context,
    knowledge_conflict_count,
    retire_knowledge,
    search_knowledge,
    show_knowledge,
    update_knowledge,
    write_knowledge_context,
)
from tools.project_memory.services.migrations import apply_migrations
from tools.project_memory.services.maintenance import format_optimization, optimize_project
from tools.project_memory.services.mcp_config import build_mcp_config, format_mcp_config, write_mcp_config
from tools.project_memory.mcp import serve_stdio
from tools.project_memory.parser_sections import (
    add_human_parser,
    add_knowledge_parser,
    add_modules_parser,
    add_rationale_parser,
    add_tasks_parser,
)
from tools.project_memory.services.modules import format_module_states, set_module_enabled
from tools.project_memory.services.rationale import (
    add_rationale,
    build_rationale_context,
    rationale_conflict_count,
    retire_rationale,
    search_rationale,
    show_rationale,
    update_rationale,
    write_rationale_context,
)
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
    written = write_context(root(), args.task, args.base, out, reset_task=args.reset_task)
    print(written)
    return 0


def command_tests(args: argparse.Namespace) -> int:
    if args.explain:
        print(explain_tests(root(), args.base), end="")
        return 0
    for command in select_tests(root(), args.base):
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
    for item in search_service(root(), args.query, args.limit, layer=args.layer, debug=args.debug):
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


def command_watch(args: argparse.Namespace) -> int:
    runs = 1 if args.once else args.max_runs
    count = 0
    while runs is None or count < runs:
        report = ensure_fresh_index(root(), "watch")
        if report:
            print("watch check: indexed")
            print(report)
        else:
            print("watch check: fresh")
        count += 1
        if args.once or (runs is not None and count >= runs):
            break
        time.sleep(max(float(args.interval), 0.1))
    return 0


def command_knowledge(args: argparse.Namespace) -> int:
    try:
        if args.knowledge_command == "add":
            result = add_knowledge(
                root(),
                item_type=args.type,
                title=args.title,
                file_path=args.file,
                entry_id=args.id,
                tags=args.tags or [],
                source=args.source,
                summary=args.summary,
                supersedes=args.supersedes,
                links=args.link or [],
            )
            print(f"knowledge added: {result.id} v{result.version} {result.path}")
            return 0
        if args.knowledge_command == "update":
            result = update_knowledge(
                root(),
                entry_id=args.id,
                file_path=args.file,
                title=args.title,
                item_type=args.type,
                tags=args.tags,
                source=args.source,
                summary=args.summary,
                links=args.link,
            )
            print(f"knowledge updated: {result.id} v{result.version} {result.path}")
            return 0
        if args.knowledge_command == "search":
            for item in search_knowledge(root(), args.query, args.limit, include_archived=args.include_archived):
                print(
                    f"[{item['type']}] {item['title']} v{item['version']} "
                    f"{item['knowledge_id']} {item['path']}: {item['snippet']}"
                )
            return 0
        if args.knowledge_command == "context":
            if args.out:
                out = Path(args.out)
                if not out.is_absolute():
                    out = root() / out
                print(write_knowledge_context(root(), args.task, out, args.limit))
            else:
                print(build_knowledge_context(root(), args.task, args.limit), end="")
            return 0
        if args.knowledge_command == "show":
            print(show_knowledge(root(), args.id), end="")
            return 0
        if args.knowledge_command == "retire":
            result = retire_knowledge(root(), args.id, status=args.status)
            print(f"knowledge {result.status}: {result.id} v{result.version} {result.path}")
            return 0
        if args.knowledge_command == "conflicts":
            print(f"knowledge conflicts: {knowledge_conflict_count(root())}")
            return 0
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("missing knowledge command", file=sys.stderr)
    return 2


def command_rationale(args: argparse.Namespace) -> int:
    try:
        if args.rationale_command == "add":
            result = add_rationale(
                root(),
                rationale_type=args.type,
                title=args.title,
                file_path=args.file,
                entry_id=args.id,
                decision=args.decision,
                why=args.why,
                rejected=args.rejected or [],
                evidence=args.evidence or [],
                tags=args.tags or [],
                source=args.source,
                summary=args.summary,
                supersedes=args.supersedes,
                links=args.link or [],
            )
            print(f"rationale added: {result.id} v{result.version} {result.path}")
            return 0
        if args.rationale_command == "update":
            result = update_rationale(
                root(),
                entry_id=args.id,
                file_path=args.file,
                title=args.title,
                rationale_type=args.type,
                decision=args.decision,
                why=args.why,
                rejected=args.rejected,
                evidence=args.evidence,
                tags=args.tags,
                source=args.source,
                summary=args.summary,
                links=args.link,
            )
            print(f"rationale updated: {result.id} v{result.version} {result.path}")
            return 0
        if args.rationale_command == "search":
            for item in search_rationale(root(), args.query, args.limit, include_archived=args.include_archived):
                print(
                    f"[{item['type']}] {item['title']} v{item['version']} "
                    f"{item['rationale_id']} {item['path']} "
                    f"[{item.get('source', 'local')} {float(item.get('score') or 0.0):.2f}]: "
                    f"{item['snippet']}"
                )
            return 0
        if args.rationale_command == "context":
            if args.out:
                out = Path(args.out)
                if not out.is_absolute():
                    out = root() / out
                print(write_rationale_context(root(), args.task, out, args.limit))
            else:
                print(build_rationale_context(root(), args.task, args.limit), end="")
            return 0
        if args.rationale_command == "show":
            print(show_rationale(root(), args.id), end="")
            return 0
        if args.rationale_command == "retire":
            result = retire_rationale(root(), args.id, status=args.status)
            print(f"rationale {result.status}: {result.id} v{result.version} {result.path}")
            return 0
        if args.rationale_command == "conflicts":
            print(f"rationale conflicts: {rationale_conflict_count(root())}")
            return 0
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("missing rationale command", file=sys.stderr)
    return 2


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

    p = sub.add_parser("watch")
    p.add_argument("--once", action="store_true")
    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--max-runs", type=int)
    p.set_defaults(func=command_watch)

    add_knowledge_parser(sub, command_knowledge)
    add_rationale_parser(sub, command_rationale)

    p = sub.add_parser("migrate")
    p.set_defaults(func=command_migrate)

    add_modules_parser(sub, command_modules)

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
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
