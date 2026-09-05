"""Bounded indexed project map. No filesystem freshness pass or model access."""
from contextlib import closing
import sqlite3

from tools.project_memory.config import config_path
from tools.project_memory.services.memory_scope import METADATA_KEYS


def memory_overview(root, limit=20):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError('limit must be between 1 and 100')
    result = dict(status='missing', filesystem_checked=False, shared_included=False,
                  axes={}, counts={}, files=[], entries=[], relations=[], truncated={})
    path = config_path(root, 'graph_db')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Overview database must stay inside project')
    if not path.is_file():
        return result
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result['status'] = 'indexed'

        def sample(name, sql, params=()):
            rows = [dict(row) for row in conn.execute(sql, (*params, limit + 1))]
            result['truncated'][name] = len(rows) > limit
            return rows[:limit]

        if 'nodes' in tables:
            result['files'] = sample('files', "SELECT substr(path,1,2048) AS path FROM nodes WHERE kind='File' ORDER BY path LIMIT ?")
            result['counts']['files'] = conn.execute("SELECT count(*) FROM nodes WHERE kind='File'").fetchone()[0]
            for axis in METADATA_KEYS:
                result['axes'][axis] = sample(axis, "SELECT coalesce(substr(json_extract(CASE WHEN json_valid(properties_json) THEN properties_json ELSE '{}' END, ?),1,128),'unclassified') AS value, count(*) AS count FROM nodes WHERE kind='File' GROUP BY value ORDER BY value LIMIT ?", ('$.' + axis,))
        entries = []
        relations = []
        for kind in ('knowledge', 'rationale'):
            if kind + '_entries' in tables:
                result['counts'][kind] = conn.execute(f'SELECT count(*) FROM {kind}_entries').fetchone()[0]
                entries.append(f"SELECT '{kind}' AS kind, substr(id,1,2048) AS id, substr(title,1,320) AS title, status FROM {kind}_entries")
            if kind + '_links' in tables:
                result['counts'][kind + '_links'] = conn.execute(f'SELECT count(*) FROM {kind}_links').fetchone()[0]
                relations.append(f"SELECT '{kind}' AS owner_kind, substr({kind}_id,1,2048) AS owner_id, substr(relation,1,64) AS relation, substr(target,1,2048) AS target FROM {kind}_links")
        if entries:
            result['entries'] = sample('entries', ' UNION ALL '.join(entries) + ' ORDER BY kind,id LIMIT ?')
        if relations:
            result['relations'] = sample('relations', ' UNION ALL '.join(relations) + ' ORDER BY owner_kind,owner_id,relation,target LIMIT ?')
        conn.rollback()
    return result
