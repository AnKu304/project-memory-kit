from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImportRef:
    module: str
    name: str | None
    alias: str | None
    line: int
    target_path: str | None = None
    kind: str = "import"


@dataclass
class Symbol:
    name: str
    fqn: str
    kind: str
    start_line: int
    end_line: int
    signature: str = ""
    docstring: str | None = None
    decorators: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)


@dataclass
class ParseResult:
    module: str
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[ImportRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
