from __future__ import annotations

import argparse
from collections.abc import Callable


CommandHandler = Callable[[argparse.Namespace], int]


def add_knowledge_parser(sub: argparse._SubParsersAction, handler: CommandHandler) -> None:
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
    k.set_defaults(func=handler)

    k = knowledge_sub.add_parser("update")
    k.add_argument("--id", required=True)
    k.add_argument("--file", required=True)
    k.add_argument("--title")
    k.add_argument("--type")
    k.add_argument("--tags", action="append")
    k.add_argument("--source")
    k.add_argument("--summary")
    k.add_argument("--link", action="append")
    k.set_defaults(func=handler)

    k = knowledge_sub.add_parser("search")
    k.add_argument("--query", required=True)
    k.add_argument("--limit", type=int, default=5)
    k.add_argument("--include-archived", action="store_true")
    k.set_defaults(func=handler)

    k = knowledge_sub.add_parser("context")
    k.add_argument("--task", required=True)
    k.add_argument("--limit", type=int)
    k.add_argument("--out")
    k.set_defaults(func=handler)

    k = knowledge_sub.add_parser("show")
    k.add_argument("--id", required=True)
    k.set_defaults(func=handler)

    k = knowledge_sub.add_parser("retire")
    k.add_argument("--id", required=True)
    k.add_argument("--status", choices=["superseded", "archived"], default="archived")
    k.set_defaults(func=handler)

    k = knowledge_sub.add_parser("conflicts")
    k.set_defaults(func=handler)


def add_rationale_parser(sub: argparse._SubParsersAction, handler: CommandHandler) -> None:
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
    r.set_defaults(func=handler)

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
    r.set_defaults(func=handler)

    r = rationale_sub.add_parser("search")
    r.add_argument("--query", required=True)
    r.add_argument("--limit", type=int, default=5)
    r.add_argument("--include-archived", action="store_true")
    r.set_defaults(func=handler)

    r = rationale_sub.add_parser("context")
    r.add_argument("--task", required=True)
    r.add_argument("--limit", type=int)
    r.add_argument("--out")
    r.set_defaults(func=handler)

    r = rationale_sub.add_parser("show")
    r.add_argument("--id", required=True)
    r.set_defaults(func=handler)

    r = rationale_sub.add_parser("retire")
    r.add_argument("--id", required=True)
    r.add_argument("--status", choices=["superseded", "archived"], default="archived")
    r.set_defaults(func=handler)

    r = rationale_sub.add_parser("conflicts")
    r.set_defaults(func=handler)


def add_modules_parser(sub: argparse._SubParsersAction, handler: CommandHandler) -> None:
    p = sub.add_parser("modules")
    modules_sub = p.add_subparsers(dest="modules_command", required=True)

    m = modules_sub.add_parser("list")
    m.set_defaults(func=handler)

    m = modules_sub.add_parser("set")
    m.add_argument("name")
    m.add_argument("--enabled", required=True)
    m.set_defaults(func=handler)


def add_tasks_parser(sub: argparse._SubParsersAction, handler: CommandHandler) -> None:
    p = sub.add_parser("tasks")
    tasks_sub = p.add_subparsers(dest="tasks_command", required=True)
    for name in ["list", "check"]:
        t = tasks_sub.add_parser(name)
        t.add_argument("--role")
        t.add_argument("--all", action="store_true")
        t.set_defaults(func=handler)
