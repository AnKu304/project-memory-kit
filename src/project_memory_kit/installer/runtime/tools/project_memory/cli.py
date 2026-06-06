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
from tools.project_memory.services.search import search as search_service
from tools.project_memory.services.test_selector import select_tests


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
    written = write_context(root(), args.task, args.base, out)
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
    for item in search_service(root(), args.query, args.limit):
        print(f"{item['path']} {item['fqn']}: {item['snippet']}")
    return 0


def command_upgrade(_: argparse.Namespace) -> int:
    print("Upgrade is installer-managed. Re-run the latest `pipx run --spec <repo> pmem init`.")
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
    p.set_defaults(func=command_search)

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

