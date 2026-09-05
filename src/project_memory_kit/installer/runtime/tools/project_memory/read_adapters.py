"""Read-only transport adapters; no initialization, freshness or model calls."""
from contextlib import closing
from pathlib import Path
import re
import sqlite3

from tools.project_memory.config import config_path
from tools.project_memory.services.memory_overview import memory_overview
from tools.project_memory.services.memory_relations import relation_details


class _ReadOnlyGraphStore:
    def __init__(self, root: Path, db_path: Path):
        self.root, self.db_path = root, db_path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path.resolve().as_uri() + '?mode=ro', uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        return connection


def read_overview(root: Path, limit: int = 20) -> dict:
    return memory_overview(root, limit)


def read_relations(root: Path, kind: str, entry_id: str, limit: int = 20) -> dict:
    if not isinstance(kind, str) or kind not in ('knowledge', 'rationale'):
        raise ValueError('kind must be knowledge or rationale')
    if not isinstance(entry_id, str) or len(entry_id) > 2048 or not re.fullmatch(r'[A-Za-z0-9_-]+', entry_id):
        raise ValueError('id must be a local record identifier')
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError('limit must be between 1 and 100')
    path = config_path(root, 'graph_db')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Relation database must stay inside project')
    result = dict(status='missing', kind=kind, id=entry_id, relations=[], truncated=False,
                  filesystem_checked=False, shared_included=False)
    if not path.is_file():
        return result
    store = _ReadOnlyGraphStore(root, path)
    with closing(store.connect()) as conn:
        row = conn.execute(f'SELECT status FROM {kind}_entries WHERE id=?', (entry_id,)).fetchone()
        if row is None:
            return {**result, 'status': 'not_found'}
        total = conn.execute(f'SELECT count(*) FROM {kind}_links WHERE {kind}_id=?', (entry_id,)).fetchone()[0]
    result.update(status='found', owner_status=row['status'], total=total, truncated=total > limit,
                  relations=relation_details(store, kind, entry_id, limit))
    return result
