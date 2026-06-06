from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.project_memory.services.context_builder import write_context
from tools.project_memory.services.doctor import doctor as doctor_service
from tools.project_memory.services.failure_memory import record_failure
from tools.project_memory.services.impact_analysis import analyze_impact, format_impact
from tools.project_memory.services.index_project import index_project
from tools.project_memory.services.init_memory import init_memory
from tools.project_memory.services.knowledge import (
    add_knowledge,
    build_knowledge_context,
    retire_knowledge,
    search_knowledge,
    show_knowledge,
    update_knowledge,
    write_knowledge_context,
)
from tools.project_memory.services.migrations import apply_migrations
from tools.project_memory.services.rationale import (
    add_rationale,
    build_rationale_context,
    retire_rationale,
    search_rationale,
    show_rationale,
    update_rationale,
    write_rationale_context,
)
from tools.project_memory.services.search import search as search_service
from tools.project_memory.services.test_selector import select_tests
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
    for item in search_service(root(), args.query, args.limit, layer=args.layer):
        print(
            f"{item['path']} {item['fqn']} "
            f"[{item.get('source', 'local')} {float(item.get('score') or 0.0):.2f}; {item.get('reason', 'matched')}]: "
            f"{item['snippet']}"
        )
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
    p.set_defaults(func=command_tests)

    p = sub.add_parser("record-failure")
    p.add_argument("--command", required=True)
    p.add_argument("--log-file", required=True)
    p.set_defaults(func=command_record_failure)

    p = sub.add_parser("search")
    p.add_argument("--query", required=True)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--layer", choices=["knowledge", "rationale"], default=None)
    p.set_defaults(func=command_search)

    p = sub.add_parser("knowledge")
    knowledge_sub = p.add_subparsers(dest="knowledge_command", required=True)

    k = knowledge_sub.add_parser("add")
    k.add_argument("--type", required=True)
    k.add_argument("--title", required=True)
    k.add_argument("--file", required=True)
    k.add_argument("--id")
    k.add_argument("--tags", action="append")
    k.add_argument("--source")
    k.add_argument("--summary")
    k.add_argument("--supersedes")
    k.add_argument("--link", action="append")
    k.set_defaults(func=command_knowledge)

    k = knowledge_sub.add_parser("update")
    k.add_argument("--id", required=True)
    k.add_argument("--file", required=True)
    k.add_argument("--title")
    k.add_argument("--type")
    k.add_argument("--tags", action="append")
    k.add_argument("--source")
    k.add_argument("--summary")
    k.add_argument("--link", action="append")
    k.set_defaults(func=command_knowledge)

    k = knowledge_sub.add_parser("search")
    k.add_argument("--query", required=True)
    k.add_argument("--limit", type=int, default=5)
    k.add_argument("--include-archived", action="store_true")
    k.set_defaults(func=command_knowledge)

    k = knowledge_sub.add_parser("context")
    k.add_argument("--task", required=True)
    k.add_argument("--limit", type=int)
    k.add_argument("--out")
    k.set_defaults(func=command_knowledge)

    k = knowledge_sub.add_parser("show")
    k.add_argument("--id", required=True)
    k.set_defaults(func=command_knowledge)

    k = knowledge_sub.add_parser("retire")
    k.add_argument("--id", required=True)
    k.add_argument("--status", choices=["superseded", "archived"], default="archived")
    k.set_defaults(func=command_knowledge)

    p = sub.add_parser("rationale")
    rationale_sub = p.add_subparsers(dest="rationale_command", required=True)

    r = rationale_sub.add_parser("add")
    r.add_argument("--type", default="decision")
    r.add_argument("--title", required=True)
    r.add_argument("--file", required=True)
    r.add_argument("--id")
    r.add_argument("--decision")
    r.add_argument("--why")
    r.add_argument("--rejected", action="append")
    r.add_argument("--evidence", action="append")
    r.add_argument("--tags", action="append")
    r.add_argument("--source")
    r.add_argument("--summary")
    r.add_argument("--supersedes")
    r.add_argument("--link", action="append")
    r.set_defaults(func=command_rationale)

    r = rationale_sub.add_parser("update")
    r.add_argument("--id", required=True)
    r.add_argument("--file", required=True)
    r.add_argument("--title")
    r.add_argument("--type")
    r.add_argument("--decision")
    r.add_argument("--why")
    r.add_argument("--rejected", action="append")
    r.add_argument("--evidence", action="append")
    r.add_argument("--tags", action="append")
    r.add_argument("--source")
    r.add_argument("--summary")
    r.add_argument("--link", action="append")
    r.set_defaults(func=command_rationale)

    r = rationale_sub.add_parser("search")
    r.add_argument("--query", required=True)
    r.add_argument("--limit", type=int, default=5)
    r.add_argument("--include-archived", action="store_true")
    r.set_defaults(func=command_rationale)

    r = rationale_sub.add_parser("context")
    r.add_argument("--task", required=True)
    r.add_argument("--limit", type=int)
    r.add_argument("--out")
    r.set_defaults(func=command_rationale)

    r = rationale_sub.add_parser("show")
    r.add_argument("--id", required=True)
    r.set_defaults(func=command_rationale)

    r = rationale_sub.add_parser("retire")
    r.add_argument("--id", required=True)
    r.add_argument("--status", choices=["superseded", "archived"], default="archived")
    r.set_defaults(func=command_rationale)

    p = sub.add_parser("migrate")
    p.set_defaults(func=command_migrate)

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
