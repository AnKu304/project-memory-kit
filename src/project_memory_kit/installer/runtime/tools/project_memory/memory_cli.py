"""Memory CLI commands, parser registration and queued-write argument preparation.

The caller supplies a root provider so command invocation uses the active CLI
root, including tests and embedders overriding it after parser construction.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable
from functools import partial
import json
from pathlib import Path
import sqlite3
import sys

from tools.project_memory.parser_sections import add_knowledge_parser, add_rationale_parser
from tools.project_memory.read_adapters import read_overview, read_relations
from tools.project_memory.write_adapters import project_local_input
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


def command_overview(get_root: Callable[[], Path], args: argparse.Namespace) -> int:
    try:
        print(json.dumps(read_overview(get_root(), args.limit), ensure_ascii=False))
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 2


def command_relations(get_root: Callable[[], Path], args: argparse.Namespace) -> int:
    try:
        print(json.dumps(read_relations(get_root(), args.kind, args.id, args.limit), ensure_ascii=False))
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 2


def command_knowledge(get_root: Callable[[], Path], args: argparse.Namespace) -> int:
    try:
        if args.knowledge_command == "add":
            result = add_knowledge(
                get_root(),
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
                get_root(),
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
            for item in search_knowledge(get_root(), args.query, args.limit, include_archived=args.include_archived):
                print(
                    f"[{item['type']}] {item['title']} v{item['version']} "
                    f"{item['knowledge_id']} {item['path']}: {item['snippet']}"
                )
            return 0
        if args.knowledge_command == "context":
            if args.out:
                out = Path(args.out)
                if not out.is_absolute():
                    out = get_root() / out
                print(write_knowledge_context(get_root(), args.task, out, args.limit))
            else:
                print(build_knowledge_context(get_root(), args.task, args.limit), end="")
            return 0
        if args.knowledge_command == "show":
            print(show_knowledge(get_root(), args.id), end="")
            return 0
        if args.knowledge_command == "retire":
            result = retire_knowledge(get_root(), args.id, status=args.status)
            print(f"knowledge {result.status}: {result.id} v{result.version} {result.path}")
            return 0
        if args.knowledge_command == "conflicts":
            print(f"knowledge conflicts: {knowledge_conflict_count(get_root())}")
            return 0
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("missing knowledge command", file=sys.stderr)
    return 2


def command_rationale(get_root: Callable[[], Path], args: argparse.Namespace) -> int:
    try:
        if args.rationale_command == "add":
            result = add_rationale(
                get_root(),
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
                get_root(),
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
            for item in search_rationale(get_root(), args.query, args.limit, include_archived=args.include_archived):
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
                    out = get_root() / out
                print(write_rationale_context(get_root(), args.task, out, args.limit))
            else:
                print(build_rationale_context(get_root(), args.task, args.limit), end="")
            return 0
        if args.rationale_command == "show":
            print(show_rationale(get_root(), args.id), end="")
            return 0
        if args.rationale_command == "retire":
            result = retire_rationale(get_root(), args.id, status=args.status)
            print(f"rationale {result.status}: {result.id} v{result.version} {result.path}")
            return 0
        if args.rationale_command == "conflicts":
            print(f"rationale conflicts: {rationale_conflict_count(get_root())}")
            return 0
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("missing rationale command", file=sys.stderr)
    return 2


def add_memory_parsers(sub: argparse._SubParsersAction, get_root: Callable[[], Path]) -> None:
    p = sub.add_parser("overview", help="Read bounded indexed memory map as JSON; no freshness/index pass")
    p.add_argument("--limit", type=int, default=20, help="Maximum samples per section (1-100)")
    p.set_defaults(func=partial(command_overview, get_root))

    p = sub.add_parser("relations", help="Read explicit relations as JSON; provenance is not verification")
    p.add_argument("--kind", choices=["knowledge", "rationale"], required=True)
    p.add_argument("--id", required=True, help="Local record ID")
    p.add_argument("--limit", type=int, default=20, help="Maximum relations (1-100)")
    p.set_defaults(func=partial(command_relations, get_root))

    add_knowledge_parser(sub, partial(command_knowledge, get_root))
    add_rationale_parser(sub, partial(command_rationale, get_root))


def prepare_memory_arguments(project_root: Path, args: argparse.Namespace) -> None:
    """Normalize typed/legacy links and recheck MCP queue replay before locking."""
    for field in getattr(args, "clear_list", None) or []:
        setattr(args, field, [])
    parsed_links = getattr(args, "links_json", None)
    if parsed_links is not None:
        args.link = (args.link or []) + parsed_links
    if getattr(args, "project_local", False):
        project_local_input(project_root, args.command, args.file)
