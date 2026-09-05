"""Path-only memory axes. Classification never broadens the project boundary."""
from __future__ import annotations

from contextlib import closing
from fnmatch import fnmatchcase
import json
from pathlib import Path
import re

from tools.project_memory.config import load_config


DOMAINS = frozenset({'frontend', 'backend', 'marketing', 'design', 'research', 'unclassified'})
TYPES = frozenset({'code', 'knowledge', 'rationale', 'agent_tooling', 'document'})
AUDIENCES = frozenset({'project', 'agent_tooling'})
METADATA_KEYS = ('memory_scope', 'memory_audience', 'memory_type', 'memory_domain')
CODE_EXTENSIONS = frozenset({
    '.py', '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.mts', '.cts', '.go', '.rs',
    '.java', '.kt', '.swift', '.c', '.cpp', '.h', '.cs', '.php', '.rb', '.vue', '.svelte', '.sql',
})


def _classification_config(cfg: dict) -> dict:
    memory = cfg.get('memory', {})
    value = memory.get('classification', {}) if isinstance(memory, dict) else None
    if not isinstance(value, dict):
        raise ValueError('memory.classification must be a mapping')
    return value


def validate_memory_classification(cfg: dict) -> None:
    """Validate all rules before indexing can write any partial result."""
    settings = _classification_config(cfg)
    domains = settings.get('domains', [])
    if not isinstance(domains, list) or any(
        not isinstance(item, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', item) for item in domains
    ):
        raise ValueError('memory.classification.domains must contain domain slugs')
    rules = settings.get('rules', [])
    if not isinstance(rules, list):
        raise ValueError('memory.classification.rules must be a list')
    allowed = {'scope': {'project'}, 'audience': AUDIENCES, 'type': TYPES, 'domain': DOMAINS | set(domains)}
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) - {'pattern', *allowed}:
            raise ValueError('Invalid memory classification rule fields')
        pattern = rule.get('pattern')
        if (not isinstance(pattern, str) or not pattern or pattern.startswith('/')
                or '\\' in pattern or '\0' in pattern or '..' in pattern.split('/')):
            raise ValueError('Classification patterns must be project-relative globs')
        for key, values in allowed.items():
            if key in rule and (not isinstance(rule[key], str) or rule[key] not in values):
                raise ValueError(f'Unsupported memory classification {key}: {rule[key]!r}')


def _relative_path(root: Path, path: Path | str) -> Path:
    raw = str(path)
    if not raw or '\\' in raw or '\0' in raw or '..' in Path(raw).parts:
        raise ValueError('Memory path must stay inside the project')
    candidate = Path(path)
    absolute = candidate if candidate.is_absolute() else root / candidate
    try:
        # Resolve only to check containment; preserve the user's in-root path for rules.
        absolute.resolve().relative_to(root.resolve())
        relative = absolute.relative_to(root)
    except ValueError as exc:
        raise ValueError('Memory path must stay inside the project') from exc
    if relative == Path('.'):
        raise ValueError('Memory path must identify a project file')
    return relative


def _default_type(rel: Path, cfg: dict) -> str:
    for kind in ('knowledge', 'rationale'):
        prefix = Path(cfg.get('paths', {}).get(f'{kind}_dir', f'.project-memory/{kind}'))
        if not prefix.is_absolute() and rel.is_relative_to(prefix):
            return kind
    parts = rel.parts
    if (rel.name in {'AGENTS.md', 'CLAUDE.md'} or '.agents' in parts or '.claude' in parts
            or '.codex' in parts or any(parts[i:i + 2] == ('tools', 'project_memory') for i in range(len(parts) - 1))):
        return 'agent_tooling'
    return 'code' if rel.suffix.lower() in CODE_EXTENSIONS else 'document'


def classify_memory_path(root: Path, path: Path | str, cfg: dict | None = None) -> dict[str, str]:
    """Return independent scope/audience/type/domain axes, never infer from text.

    First matching configured rule overrides path defaults. Shared memory is not
    implemented: even an explicit shared scope is rejected, not silently enabled.
    """
    cfg = load_config(root) if cfg is None else cfg
    validate_memory_classification(cfg)
    root = root.absolute()
    rel = _relative_path(root, path)
    kind = _default_type(rel, cfg)
    aliases = {'front': 'frontend', 'back': 'backend'}
    domain = next((aliases.get(part, part) for part in rel.parts[:-1]
                   if aliases.get(part, part) in DOMAINS - {'unclassified'}), 'unclassified')
    metadata = dict(memory_scope='project', memory_audience='agent_tooling' if kind == 'agent_tooling' else 'project',
                    memory_type=kind, memory_domain=domain)
    for rule in _classification_config(cfg).get('rules', []):
        if fnmatchcase(rel.as_posix(), rule['pattern']):
            metadata.update({f'memory_{key}': rule[key] for key in ('scope', 'audience', 'type', 'domain') if key in rule})
            break
    return metadata


def indexed_memory_metadata(store) -> dict[str, dict]:
    """One explicitly closed snapshot, not an extra connection per skipped file."""
    with closing(store.connect()) as connection:
        rows = connection.execute("SELECT path, properties_json FROM nodes WHERE kind = 'File'")
        parsed = ((row['path'], json.loads(row['properties_json'])) for row in rows)
        return {path: {key: props.get(key) for key in METADATA_KEYS} for path, props in parsed}


def annotate_indexed_path(store, path: str, metadata: dict[str, str]) -> None:
    """Merge axes into generated nodes without changing legacy layer or properties."""
    with closing(store.connect()) as connection, connection:
        rows = connection.execute(
            "SELECT id, properties_json FROM nodes WHERE path = ? AND kind IN ('File', 'Module', 'Symbol', 'Chunk', 'Route')",
            (path,),
        )
        updates = [(json.dumps({**json.loads(row['properties_json']), **metadata}, sort_keys=True), row['id'])
                   for row in rows]
        connection.executemany('UPDATE nodes SET properties_json = ? WHERE id = ?', updates)


def existing_file_with_metadata(store, path: str, metadata: dict[str, str]) -> str | None:
    """Reuse an indexed import target without replacing its graph attributes.

    Import placeholders know only a path. They cannot replace source-owned
    properties, hash, language, layer, or provenance on an existing File node.
    """
    node_id = store.node_id('File', path=path, fqn=path, name=Path(path).name)
    with closing(store.connect()) as connection, connection:
        row = connection.execute('SELECT properties_json FROM nodes WHERE id=?', (node_id,)).fetchone()
        if row is None:
            return None
        props = {**json.loads(row['properties_json']), **metadata}
        connection.execute('UPDATE nodes SET properties_json=? WHERE id=?', (json.dumps(props, sort_keys=True), node_id))
    return node_id
