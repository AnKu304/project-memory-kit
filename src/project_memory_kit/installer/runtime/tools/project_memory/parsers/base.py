from __future__ import annotations

from pathlib import Path

from tools.project_memory.parsers.symbol_model import ParseResult


class Parser:
    def parse(self, root: Path, path: Path) -> ParseResult:  # pragma: no cover - interface only
        raise NotImplementedError

