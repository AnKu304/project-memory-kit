"""Explicit local assertions; provenance and confidence never establish truth.

Markdown pmem_links is the durable representation. Existing SQLite link tables
are its projection. Legacy string links retain their historical interpretation.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import re

from tools.project_memory.config import load_config
from tools.project_memory.hashing import stable_id
from tools.project_memory.services.memory_scope import DOMAINS, validate_memory_classification
from tools.project_memory.time_utils import utc_now

RELATIONS = frozenset({'causes', 'supports', 'contradicts', 'depends_on', 'derived_from',
                       'supersedes', 'affects', 'documented_in'})
MAX_LINKS = 100


def _kind(kind):
    if kind not in ('knowledge', 'rationale'):
        raise ValueError('Owner must be knowledge or rationale')
    return kind



def _query(store, sql, params=()):
    if not store.db_path.resolve().is_relative_to(store.root.resolve()):
        raise ValueError('Relation database must stay inside project')
    with closing(store.connect()) as conn:
        return conn.execute(sql, params).fetchall()


def _text(value, label, maximum=2048):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or '\0' in value:
        raise ValueError(f'Invalid {label}')
    return value


def local_file(root, value):
    """Resolve only explicit project-relative files; never traverse another root."""
    value = _text(value, 'local path')
    path = Path(value)
    if path.is_absolute() or '\\' in value or '..' in path.parts:
        raise ValueError('Path must stay inside project')
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError('Local file does not exist inside project')
    return resolved


def links_from_markdown(content):
    """Read our single JSON-valued YAML key without parsing legacy free-form YAML."""
    if not content.startswith('---\n'):
        return []
    end = content.find('\n---', 4)
    if end < 0:
        return []
    lines = [line for line in content[4:end].splitlines() if line.startswith('pmem_links:')]
    if not lines:
        return []
    if len(lines) != 1:
        raise ValueError('Duplicate pmem_links frontmatter')
    try:
        result = json.loads(lines[0].partition(':')[2])
    except (ValueError, TypeError) as exc:
        raise ValueError('pmem_links must be a JSON array') from exc
    if not isinstance(result, list) or len(result) > MAX_LINKS:
        raise ValueError('pmem_links must be a bounded array')
    return result


def with_links(markdown, links, kind):
    """Insert lossless JSON (also valid YAML) into generated frontmatter."""
    end = markdown.find('\n---', 4)
    if not markdown.startswith('---\n') or end < 0:
        raise ValueError('Generated entry must have frontmatter')
    _kind(kind)
    return (markdown[:end] + '\npmem_links_kind: ' + kind + '\npmem_links: '
            + json.dumps(links, ensure_ascii=False, allow_nan=False) + markdown[end:])


def validate_links(store, kind, entry_id, links, owner_path=None):
    _kind(kind)
    cfg = load_config(store.root)
    validate_memory_classification(cfg)
    domains = DOMAINS | set(cfg.get('memory', {}).get('classification', {}).get('domains', []))
    result = []
    for link in links:
        if len(result) >= MAX_LINKS:
            raise ValueError('Too many links')
        if isinstance(link, str):
            if link.strip():
                result.append(_text(link.strip(), 'legacy link'))
            continue
        if not isinstance(link, dict) or set(link) != {'relation', 'target', 'source', 'evidence', 'confidence', 'status'}:
            raise ValueError('Invalid structured relation fields')
        if not isinstance(link['relation'], str) or link['relation'] not in RELATIONS:
            raise ValueError('Unknown relation type')
        target = link['target']
        if not isinstance(target, dict) or set(target) != {'kind', 'id'}:
            raise ValueError('Target must contain only local kind and id')
        target_kind = _text(target['kind'], 'target kind', 32)
        target_id = _text(target['id'], 'target id')
        if target_kind in ('knowledge', 'rationale'):
            if target_kind == kind and target_id == entry_id:
                raise ValueError('Self relation is forbidden')
            if not re.fullmatch(r'[A-Za-z0-9_-]+', target_id):
                raise ValueError('Target id must be project local')
            rows = _query(store, f'SELECT path FROM {target_kind}_entries WHERE id=?', (target_id,))
            if not rows:
                raise ValueError('Target entry does not exist')
            local_file(store.root, rows[0]['path'])
        elif target_kind == 'file':
            target_path = local_file(store.root, target_id)
            own = _query(store, f'SELECT path FROM {kind}_entries WHERE id=?', (entry_id,))
            if ((own and target_path == (store.root / own[0]['path']).resolve())
                    or (owner_path is not None and target_path == owner_path.resolve())):
                raise ValueError('Self relation is forbidden')
        elif target_kind == 'domain':
            if target_id not in domains:
                raise ValueError('Unknown configured domain')
        else:
            raise ValueError('Unknown target kind')
        source = link['source']
        if not isinstance(source, dict) or set(source) != {'path', 'revision'}:
            raise ValueError('Source requires local path and SHA-256 revision')
        local_file(store.root, source['path'])
        if not isinstance(source['revision'], str) or not re.fullmatch(r'[0-9a-f]{64}', source['revision']):
            raise ValueError('Source revision must be SHA-256')
        confidence = link['confidence']
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError('Confidence must be finite within 0..1')
        if not isinstance(link['status'], str) or link['status'] not in ('current', 'archived'):
            raise ValueError('Invalid relation lifecycle')
        evidence = link['evidence']
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 20:
            raise ValueError('Explicit bounded evidence references required')
        for reference in evidence:
            _text(reference, 'evidence reference')
        result.append(json.loads(json.dumps(link, allow_nan=False)))
    return result


def save_links(store, kind, entry_id, links):
    """Project a prevalidated batch; caller must validate before writing its note."""
    _kind(kind)
    now = utc_now()
    with closing(store.connect()) as conn, conn:
        conn.execute(f'DELETE FROM {kind}_links WHERE {kind}_id=?', (entry_id,))
        for ordinal, link in enumerate(links):
            if isinstance(link, str):
                relation, _, target = link.partition(':')
                if not target:
                    relation, target = 'relates_to', relation
                props = {'pmem_legacy': link, 'ordinal': ordinal}
            else:
                relation = link['relation']
                target = link['target']['kind'] + ':' + link['target']['id']
                props = {'pmem_relation': link, 'ordinal': ordinal}
            link_id = stable_id(kind + '-link', entry_id, relation, target, str(ordinal))
            conn.execute(f'INSERT INTO {kind}_links VALUES (?, ?, ?, ?, ?, ?)',
                         (link_id, entry_id, relation, target, json.dumps(props), now))


def load_links(store, kind, entry_id, limit=None):
    _kind(kind)
    sql = (f'SELECT * FROM {kind}_links WHERE {kind}_id=? '
           "ORDER BY coalesce(json_extract(properties_json, '$.ordinal'), 0), created_at, id")
    rows = _query(store, sql + (' LIMIT ?' if limit is not None else ''),
                  (entry_id, limit) if limit is not None else (entry_id,))
    values = []
    for row in rows:
        props = json.loads(row['properties_json'])
        value = props.get('pmem_relation', props.get('pmem_legacy', row['relation'] + ':' + row['target']))
        values.append((props.get('ordinal', len(values)), value))
    return [value for _, value in sorted(values, key=lambda item: item[0])]


def restore_links(store, kind, entry_id, markdown):
    """Explicit second restore phase: all owning/target entries must already exist."""
    _kind(kind)
    end = markdown.find('\n---', 4)
    header = markdown[4:end].splitlines() if markdown.startswith('---\n') and end > 0 else []
    if ([line for line in header if line.startswith('pmem_id:')] != [f'pmem_id: {entry_id}']
            or [line for line in header if line.startswith('pmem_links_kind:')] != [f'pmem_links_kind: {kind}']
            or not any(line.startswith('pmem_links:') for line in header)):
        raise ValueError('Restore Markdown must identify the same owner and explicit links')
    if not _query(store, f'SELECT id FROM {kind}_entries WHERE id=?', (entry_id,)):
        raise ValueError('Restore owner first')
    links = validate_links(store, kind, entry_id, links_from_markdown(markdown))
    save_links(store, kind, entry_id, links)
    return len(links)


def relation_details(store, kind, entry_id, limit=20):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LINKS:
        raise ValueError('limit must be between 1 and 100')
    result = []
    for link in load_links(store, kind, entry_id, limit=limit):
        detail = {'link': link, 'verified': False, 'source_revision_status': 'unknown', 'target_status': 'unknown'}
        if isinstance(link, dict):
            try:
                path = local_file(store.root, link['source']['path'])
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(65536), b''):
                        digest.update(chunk)
                detail['source_revision_status'] = 'matches' if digest.hexdigest() == link['source']['revision'] else 'stale'
            except (ValueError, OSError):
                detail['source_revision_status'] = 'unavailable'
            target = link['target']
            if target['kind'] in ('knowledge', 'rationale'):
                rows = _query(store, f"SELECT status FROM {target['kind']}_entries WHERE id=?", (target['id'],))
                detail['target_status'] = rows[0]['status'] if rows else 'missing'
            detail['status'] = link['status']
        result.append(detail)
    return result
