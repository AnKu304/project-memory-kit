from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from tools.project_memory.parsers.js_ts_imports import (
    module_name_for_path,
    resolve_module,
)
from tools.project_memory.parsers.symbol_model import ImportRef, ParseResult, Symbol


_IDENT = r"[A-Za-z_$][A-Za-z0-9_$]*"
_CALL_RE = re.compile(rf"\b({_IDENT}(?:\.{_IDENT})*)\s*(?:<[^>\n]*>)?\(")
_IDENT_RE = re.compile(rf"\b({_IDENT})\b")
_JSX_TAG_RE = re.compile(rf"<\s*([A-Z][A-Za-z0-9_$.]*)\b")
_CLASS_RE = re.compile(rf"\b(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+({_IDENT})(?:\s+extends\s+({_IDENT}(?:\.{_IDENT})?))?", re.M)
_FUNCTION_RE = re.compile(rf"\b(?:export\s+)?(?:default\s+)?(?:async\s+)?function(?:\s*\*)?\s+({_IDENT})\s*\(", re.M)
_DEFAULT_FUNCTION_RE = re.compile(r"\bexport\s+default\s+(?:async\s+)?function(?:\s*\*)?\s*\(", re.M)
_VAR_FUNCTION_RE = re.compile(
    rf"\b(?:export\s+)?(?:const|let|var)\s+({_IDENT})\s*(?:<[^=;]+>)?\s*(?::[^=;]+)?=\s*"
    rf"(?:async\s*)?(?:function\b|(?:\([^)]*\)|{_IDENT})\s*=>)",
    re.M,
)
_METHOD_RE = re.compile(
    rf"^[ \t]*(?:(?:public|private|protected|static|async|readonly|override|get|set)\s+)*"
    rf"({_IDENT}|constructor)\s*(?:<[^>{{}}]*>)?\([^;{{}}]*\)\s*(?::[^{{;]+)?\{{",
    re.M,
)
_PROPERTY_METHOD_RE = re.compile(
    rf"^[ \t]*(?:(?:public|private|protected|static|readonly|override)\s+)*"
    rf"({_IDENT})\s*(?::[^=;]+)?=\s*(?:async\s*)?(?:\([^)]*\)|{_IDENT})\s*=>",
    re.M,
)
_STATIC_IMPORT_RE = re.compile(
    r"\bimport\s+(?:(?P<clause>[\s\S]*?)\s+from\s+)?['\"](?P<module>[^'\"]+)['\"]",
    re.M,
)
_EXPORT_FROM_RE = re.compile(r"\bexport\s+(?P<clause>\*|(?:type\s+)?\{[\s\S]*?\})\s+from\s+['\"](?P<module>[^'\"]+)['\"]", re.M)
_REQUIRE_RE = re.compile(r"\brequire\(\s*['\"]([^'\"]+)['\"]\s*\)")
_DYNAMIC_IMPORT_RE = re.compile(r"\bimport\(\s*['\"]([^'\"]+)['\"]\s*\)")

_CALL_EXCLUDES = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
    "function",
    "return",
    "typeof",
    "new",
    "class",
    "super",
}
_REF_EXCLUDES = _CALL_EXCLUDES | {
    "const",
    "let",
    "var",
    "import",
    "export",
    "from",
    "as",
    "default",
    "async",
    "await",
    "extends",
    "implements",
    "interface",
    "type",
    "public",
    "private",
    "protected",
    "static",
    "readonly",
    "return",
    "true",
    "false",
    "null",
    "undefined",
}


class JsTsParser:
    def parse(self, root: Path, path: Path) -> ParseResult:
        module = module_name_for_path(root, path)
        result = self._parse_with_typescript(root, path, module)
        if result is None:
            result = self._parse_lexical(path, module)
        for item in result.imports:
            item.target_path = resolve_module(root, path, item.module)
        return result

    def _parse_with_typescript(self, root: Path, path: Path, module: str) -> ParseResult | None:
        node = shutil.which("node")
        if not node:
            return None
        script = Path(__file__).with_name("js_ts_parser.js")
        try:
            completed = subprocess.run(
                [node, str(script), str(root), str(path), module],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
            )
        except Exception:
            return None
        if completed.returncode != 0:
            return None
        try:
            data = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return None
        if not data.get("ok"):
            return None
        return ParseResult(
            module=module,
            symbols=[_symbol_from_json(item) for item in data.get("symbols", [])],
            imports=[_import_from_json(item) for item in data.get("imports", [])],
            warnings=[str(item) for item in data.get("warnings", [])],
        )

    def _parse_lexical(self, path: Path, module: str) -> ParseResult:
        source = path.read_text(encoding="utf-8", errors="replace")
        comment_clean = _strip_js_comments(source)
        clean = _strip_js_comments_and_strings(source)
        line_starts = _line_starts(clean)
        imports = _parse_imports(comment_clean, line_starts)
        symbols = _parse_symbols(source, clean, line_starts, module)
        return ParseResult(module=module, imports=imports, symbols=symbols)


def _symbol_from_json(item: dict[str, Any]) -> Symbol:
    return Symbol(
        name=str(item.get("name") or ""),
        fqn=str(item.get("fqn") or item.get("name") or ""),
        kind=str(item.get("kind") or "function"),
        start_line=int(item.get("start_line") or 1),
        end_line=int(item.get("end_line") or item.get("start_line") or 1),
        signature=str(item.get("signature") or ""),
        docstring=item.get("docstring"),
        decorators=[str(value) for value in item.get("decorators", [])],
        bases=[str(value) for value in item.get("bases", [])],
        calls=sorted({str(value) for value in item.get("calls", []) if value}),
        references=sorted({str(value) for value in item.get("references", []) if value}),
    )


def _import_from_json(item: dict[str, Any]) -> ImportRef:
    return ImportRef(
        module=str(item.get("module") or ""),
        name=item.get("name"),
        alias=item.get("alias"),
        line=int(item.get("line") or 1),
    )


def _parse_imports(clean: str, line_starts: list[int]) -> list[ImportRef]:
    imports: list[ImportRef] = []
    seen: set[tuple[str, str | None, str | None, int]] = set()

    def add(module: str, name: str | None, alias: str | None, offset: int) -> None:
        line = _line_number(line_starts, offset)
        key = (module, name, alias, line)
        if key not in seen:
            seen.add(key)
            imports.append(ImportRef(module=module, name=name, alias=alias, line=line))

    for match in _STATIC_IMPORT_RE.finditer(clean):
        module = match.group("module")
        clause = match.group("clause")
        for name, alias in _names_from_import_clause(clause):
            add(module, name, alias, match.start())
    for match in _EXPORT_FROM_RE.finditer(clean):
        module = match.group("module")
        for name, alias in _names_from_import_clause(match.group("clause")):
            add(module, name, alias, match.start())
    for regex in (_REQUIRE_RE, _DYNAMIC_IMPORT_RE):
        for match in regex.finditer(clean):
            add(match.group(1), None, None, match.start())
    return imports


def _names_from_import_clause(clause: str | None) -> list[tuple[str | None, str | None]]:
    if not clause:
        return [(None, None)]
    clause = re.sub(r"\btype\s+", "", clause.strip())
    names: list[tuple[str | None, str | None]] = []
    if clause.startswith("*"):
        match = re.search(r"\*\s+as\s+(" + _IDENT + ")", clause)
        return [("*", match.group(1) if match else None)]
    before_named = clause.split("{", 1)[0].strip().strip(",")
    if before_named and before_named not in {"type", "*"}:
        names.append(("default", before_named.split(",", 1)[0].strip()))
    named = re.search(r"\{(?P<body>[\s\S]*?)\}", clause)
    if named:
        for raw in named.group("body").split(","):
            item = raw.strip()
            if not item:
                continue
            parts = re.split(r"\s+as\s+", item)
            name = parts[0].strip()
            alias = parts[1].strip() if len(parts) > 1 else None
            names.append((name, alias))
    return names or [(None, None)]


def _parse_symbols(source: str, clean: str, line_starts: list[int], module: str) -> list[Symbol]:
    symbols: list[Symbol] = []
    class_spans: list[tuple[str, int, int]] = []

    for match in _CLASS_RE.finditer(clean):
        name = match.group(1)
        start_line = _line_number(line_starts, match.start())
        end_line, body_start, body_end = _range_for_block(clean, line_starts, match.end())
        class_spans.append((name, body_start, body_end))
        symbols.append(
            Symbol(
                name=name,
                fqn=f"{module}.{name}",
                kind="class",
                start_line=start_line,
                end_line=end_line,
                signature=_line_text(source, start_line),
                bases=[match.group(2)] if match.group(2) else [],
            )
        )
        body_clean = clean[body_start:body_end]
        for method_match in list(_METHOD_RE.finditer(body_clean)) + list(_PROPERTY_METHOD_RE.finditer(body_clean)):
            method_name = method_match.group(1)
            method_abs = body_start + method_match.start()
            method_line = _line_number(line_starts, method_abs)
            method_end, _, _ = _range_for_block(clean, line_starts, body_start + method_match.end())
            body = _body_between_lines(source, method_line, method_end)
            calls, refs = _usage(body)
            symbols.append(
                Symbol(
                    name=method_name,
                    fqn=f"{module}.{name}.{method_name}",
                    kind="method",
                    start_line=method_line,
                    end_line=method_end,
                    signature=_line_text(source, method_line),
                    calls=calls,
                    references=refs,
                )
            )

    for match in _FUNCTION_RE.finditer(clean):
        if _inside_spans(match.start(), class_spans):
            continue
        name = match.group(1)
        start_line = _line_number(line_starts, match.start())
        end_line, _, _ = _range_for_block(clean, line_starts, match.end())
        body = _body_between_lines(source, start_line, end_line)
        calls, refs = _usage(body)
        symbols.append(
            Symbol(
                name=name,
                fqn=f"{module}.{name}",
                kind="function",
                start_line=start_line,
                end_line=end_line,
                signature=_line_text(source, start_line),
                calls=calls,
                references=refs,
            )
        )

    for match in _DEFAULT_FUNCTION_RE.finditer(clean):
        if _inside_spans(match.start(), class_spans):
            continue
        start_line = _line_number(line_starts, match.start())
        end_line, _, _ = _range_for_block(clean, line_starts, match.end())
        body = _body_between_lines(source, start_line, end_line)
        calls, refs = _usage(body)
        symbols.append(
            Symbol(
                name="default",
                fqn=f"{module}.default",
                kind="function",
                start_line=start_line,
                end_line=end_line,
                signature=_line_text(source, start_line),
                calls=calls,
                references=refs,
            )
        )

    for match in _VAR_FUNCTION_RE.finditer(clean):
        if _inside_spans(match.start(), class_spans):
            continue
        name = match.group(1)
        start_line = _line_number(line_starts, match.start())
        end_line, _, _ = _range_for_block(clean, line_starts, match.end())
        body = _body_between_lines(source, start_line, end_line)
        calls, refs = _usage(body)
        symbols.append(
            Symbol(
                name=name,
                fqn=f"{module}.{name}",
                kind="function",
                start_line=start_line,
                end_line=end_line,
                signature=_line_text(source, start_line),
                calls=calls,
                references=refs,
            )
        )

    return _dedupe_symbols(symbols)


def _usage(body: str) -> tuple[list[str], list[str]]:
    calls = {
        match.group(1)
        for match in _CALL_RE.finditer(body)
        if match.group(1).split(".", 1)[0] not in _CALL_EXCLUDES
    }
    jsx_refs = {match.group(1) for match in _JSX_TAG_RE.finditer(body)}
    refs = {
        match.group(1)
        for match in _IDENT_RE.finditer(body)
        if match.group(1) not in _REF_EXCLUDES and not match.group(1)[0].isdigit()
    }
    refs.update(jsx_refs)
    calls.update(jsx_refs)
    return sorted(calls), sorted(refs)


def _strip_js_comments_and_strings(source: str) -> str:
    chars = list(source)
    i = 0
    quote: str | None = None
    while i < len(chars):
        char = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if quote:
            if char == "\\":
                chars[i] = " "
                if i + 1 < len(chars) and chars[i + 1] != "\n":
                    chars[i + 1] = " "
                i += 2
                continue
            if char == quote:
                quote = None
            if char != "\n":
                chars[i] = " "
            i += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            chars[i] = " "
            i += 1
            continue
        if char == "/" and nxt == "/":
            chars[i] = chars[i + 1] = " "
            i += 2
            while i < len(chars) and chars[i] != "\n":
                chars[i] = " "
                i += 1
            continue
        if char == "/" and nxt == "*":
            chars[i] = chars[i + 1] = " "
            i += 2
            while i + 1 < len(chars) and not (chars[i] == "*" and chars[i + 1] == "/"):
                if chars[i] != "\n":
                    chars[i] = " "
                i += 1
            if i + 1 < len(chars):
                chars[i] = chars[i + 1] = " "
                i += 2
            continue
        i += 1
    return "".join(chars)


def _strip_js_comments(source: str) -> str:
    chars = list(source)
    i = 0
    quote: str | None = None
    while i < len(chars):
        char = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if quote:
            if char == "\\":
                i += 2
                continue
            if char == quote:
                quote = None
            i += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            i += 1
            continue
        if char == "/" and nxt == "/":
            chars[i] = chars[i + 1] = " "
            i += 2
            while i < len(chars) and chars[i] != "\n":
                chars[i] = " "
                i += 1
            continue
        if char == "/" and nxt == "*":
            chars[i] = chars[i + 1] = " "
            i += 2
            while i + 1 < len(chars) and not (chars[i] == "*" and chars[i + 1] == "/"):
                if chars[i] != "\n":
                    chars[i] = " "
                i += 1
            if i + 1 < len(chars):
                chars[i] = chars[i + 1] = " "
                i += 2
            continue
        i += 1
    return "".join(chars)


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


def _line_number(line_starts: list[int], offset: int) -> int:
    low = 0
    high = len(line_starts)
    while low < high:
        mid = (low + high) // 2
        if line_starts[mid] <= offset:
            low = mid + 1
        else:
            high = mid
    return max(1, low)


def _range_for_block(clean: str, line_starts: list[int], search_from: int) -> tuple[int, int, int]:
    open_at = clean.find("{", search_from)
    if open_at == -1:
        line = _line_number(line_starts, search_from)
        return line, search_from, search_from
    depth = 0
    for index in range(open_at, len(clean)):
        if clean[index] == "{":
            depth += 1
        elif clean[index] == "}":
            depth -= 1
            if depth == 0:
                return _line_number(line_starts, index), open_at + 1, index
    return _line_number(line_starts, len(clean) - 1), open_at + 1, len(clean)


def _inside_spans(offset: int, spans: list[tuple[str, int, int]]) -> bool:
    return any(start <= offset <= end for _, start, end in spans)


def _body_between_lines(source: str, start_line: int, end_line: int) -> str:
    lines = source.splitlines()
    return "\n".join(lines[max(start_line - 1, 0) : max(end_line, start_line)])


def _line_text(source: str, line: int) -> str:
    lines = source.splitlines()
    if not 1 <= line <= len(lines):
        return ""
    return lines[line - 1].strip()[:300]


def _dedupe_symbols(symbols: list[Symbol]) -> list[Symbol]:
    seen: set[tuple[str, int]] = set()
    result: list[Symbol] = []
    for symbol in sorted(symbols, key=lambda item: (item.start_line, item.fqn)):
        key = (symbol.fqn, symbol.start_line)
        if key in seen:
            continue
        seen.add(key)
        result.append(symbol)
    return result
