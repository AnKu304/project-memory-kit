from __future__ import annotations

import ast
import symtable
from pathlib import Path

from tools.project_memory.parsers.python_imports import module_name_for_path, resolve_module
from tools.project_memory.parsers.symbol_model import ImportRef, ParseResult, Symbol


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.Call):
        return _name(node.func)
    if isinstance(node, ast.Constant):
        return repr(node.value)
    return node.__class__.__name__


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = []
    for arg in [*node.args.posonlyargs, *node.args.args]:
        args.append(arg.arg)
    if node.args.vararg:
        args.append("*" + node.args.vararg.arg)
    for arg in node.args.kwonlyargs:
        args.append(arg.arg)
    if node.args.kwarg:
        args.append("**" + node.args.kwarg.arg)
    return f"{node.name}({', '.join(args)})"


class _Collector(ast.NodeVisitor):
    def __init__(self, module: str):
        self.module = module
        self.class_stack: list[str] = []
        self.symbols: list[Symbol] = []
        self.imports: list[ImportRef] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(ImportRef(alias.name, None, alias.asname, node.lineno))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        for alias in node.names:
            self.imports.append(ImportRef(module, alias.name, alias.asname, node.lineno))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        fqn = ".".join([self.module, *self.class_stack, node.name])
        symbol = Symbol(
            name=node.name,
            fqn=fqn,
            kind="class",
            start_line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            docstring=ast.get_docstring(node),
            decorators=[_name(item) for item in node.decorator_list],
            bases=[_name(item) for item in node.bases],
        )
        self.symbols.append(symbol)
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node, "method" if self.class_stack else "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, "async_method" if self.class_stack else "async_function")

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> None:
        fqn = ".".join([self.module, *self.class_stack, node.name])
        calls: list[str] = []
        refs: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                calls.append(_name(child.func))
            elif isinstance(child, ast.Name):
                refs.append(child.id)
        self.symbols.append(
            Symbol(
                name=node.name,
                fqn=fqn,
                kind=kind,
                start_line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                signature=_signature(node),
                docstring=ast.get_docstring(node),
                decorators=[_name(item) for item in node.decorator_list],
                calls=sorted(set(calls)),
                references=sorted(set(refs)),
            )
        )
        self.generic_visit(node)


class PythonAstParser:
    def parse(self, root: Path, path: Path) -> ParseResult:
        module = module_name_for_path(root, path)
        source = path.read_text(encoding="utf-8", errors="replace")
        result = ParseResult(module=module)
        try:
            tree = ast.parse(source, filename=str(path))
            symtable.symtable(source, str(path), "exec")
        except SyntaxError as exc:
            result.warnings.append(f"SyntaxError: {exc.msg} at line {exc.lineno}")
            return result
        except Exception as exc:
            result.warnings.append(f"Parser warning: {exc}")
        collector = _Collector(module)
        collector.visit(tree)
        for item in collector.imports:
            raw_module = item.module.lstrip(".")
            level = len(item.module) - len(raw_module)
            item.target_path = resolve_module(root, path, raw_module, level)
        result.imports = collector.imports
        result.symbols = collector.symbols
        return result

