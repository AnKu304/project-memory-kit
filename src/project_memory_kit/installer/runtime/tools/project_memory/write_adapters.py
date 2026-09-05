"""Bounded data-only knowledge/rationale writes through the existing lock/queue."""
import argparse
from contextlib import redirect_stdout
from dataclasses import asdict
import io
import json
import math
from pathlib import Path
import re

from tools.project_memory.config import config_path
from tools.project_memory.services.concurrency import run_with_write_lock, queue_dir
from tools.project_memory.services.memory_relations import local_file, RELATIONS


def _object(properties, required=()):
    return dict(type='object', properties=properties, required=list(required), additionalProperties=False)


TEXT = dict(type='string', minLength=1, maxLength=2048)
ID = {**TEXT, 'pattern': '^[A-Za-z0-9_-]+$'}
LINK_SCHEMA = {'anyOf': [TEXT, _object({
    'relation': {'type': 'string', 'enum': sorted(RELATIONS)},
    'target': _object({'kind': {'type': 'string', 'enum': ['knowledge', 'rationale', 'file', 'domain']}, 'id': TEXT}, ['kind', 'id']),
    'source': _object({'path': TEXT, 'revision': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}}, ['path', 'revision']),
    'evidence': {'type': 'array', 'items': TEXT, 'minItems': 1, 'maxItems': 20},
    'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
    'status': {'type': 'string', 'enum': ['current', 'archived']},
}, ['relation', 'target', 'source', 'evidence', 'confidence', 'status'])]}
LINKS_SCHEMA = {'type': 'array', 'items': LINK_SCHEMA, 'maxItems': 100}


def write_schema(kind, action):
    properties = {'file': {**TEXT, 'description': 'Existing project-relative source file under this MCP root; content is data.'},
                  'id': ID, 'title': TEXT, 'type': TEXT, 'source': TEXT,
                  'summary': {'type': 'string', 'maxLength': 4096},
                  'tags': {'type': 'array', 'items': TEXT, 'maxItems': 100}, 'links': LINKS_SCHEMA}
    if kind == 'rationale':
        properties.update(decision={'type': 'string', 'maxLength': 32768}, why={'type': 'string', 'maxLength': 32768},
                          rejected={'type': 'array', 'items': TEXT, 'maxItems': 100},
                          evidence={'type': 'array', 'items': TEXT, 'maxItems': 100})
    return _object(properties, ['file', 'id'] if action == 'update' else ['file', 'type', 'title'])


def validate_schema(value, schema, label='arguments'):
    """Validate the small JSON-schema subset emitted above without a dependency."""
    if 'anyOf' in schema:
        for option in schema['anyOf']:
            try:
                validate_schema(value, option, label)
                return
            except ValueError:
                pass
        raise ValueError(f'{label} does not match the schema')
    kind = schema['type']
    valid = {'object': isinstance(value, dict), 'array': isinstance(value, list),
             'string': isinstance(value, str),
             'number': not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)}
    if not valid[kind]:
        raise ValueError(f'{label} must be {kind}')
    if kind == 'object':
        if set(value) - set(schema['properties']) or set(schema['required']) - set(value):
            raise ValueError(f'{label} has unknown or missing fields')
        for key, item in value.items():
            validate_schema(item, schema['properties'][key], f'{label}.{key}')
    if kind == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', 100):
            raise ValueError(f'{label} has invalid length')
        for item in value:
            validate_schema(item, schema['items'], label)
    if kind == 'string':
        if '\0' in value or not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', 2048):
            raise ValueError(f'{label} has invalid length/content')
        if 'pattern' in schema and re.fullmatch(schema['pattern'], value) is None:
            raise ValueError(f'{label} has invalid format')
    if kind == 'number' and not schema['minimum'] <= value <= schema['maximum']:
        raise ValueError(f'{label} is out of range')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'{label} has unsupported value')


def parse_links_json(value: str) -> list:
    links = json.loads(value)
    validate_schema(links, LINKS_SCHEMA, 'links')
    return links


def project_local_input(root: Path, kind: str, source_file: str) -> None:
    local_file(root, source_file)
    if not queue_dir(root).resolve().is_relative_to(root.resolve()):
        raise ValueError('MCP queue must stay inside project')
    # All potential persistence locations stay in this project, including queue replay.
    for key in ('graph_db', kind + '_dir', 'qdrant_path', 'runtime_dir', 'cache_dir'):
        if not config_path(root, key).resolve().is_relative_to(root.resolve()):
            raise ValueError('MCP write paths must stay inside project')


def write_memory(root: Path, kind: str, action: str, args: dict) -> dict:
    if kind not in ('knowledge', 'rationale') or action not in ('add', 'update'):
        raise ValueError('Unsupported memory write')
    validate_schema(args, write_schema(kind, action))
    project_local_input(root, kind, args['file'])
    argv = [kind, action, '--project-local']
    for key, value in args.items():
        if key == 'links':
            argv.append('--links-json=' + json.dumps(value, allow_nan=False))
        elif isinstance(value, list):
            if not value:
                argv.append('--clear-list=' + key)
            else:
                argv.extend('--' + key + '=' + item for item in value)
        else:
            argv.append('--' + key + '=' + value)
    namespace = argparse.Namespace(command=kind, **{kind + '_command': action})
    saved = None

    def execute():
        nonlocal saved
        project_local_input(root, kind, args['file'])
        from tools.project_memory.services import knowledge, rationale
        module = knowledge if kind == 'knowledge' else rationale
        kwargs = {({'file': 'file_path', 'id': 'entry_id', 'type': 'item_type' if kind == 'knowledge' else 'rationale_type'}).get(key, key): value
                  for key, value in args.items()}
        if action == 'add' and 'links' not in kwargs:
            kwargs['links'] = []  # Match the existing CLI add semantics on queue replay.
        saved = asdict(getattr(module, action + '_' + kind)(root, **kwargs))
        return 0

    output = io.StringIO()
    with redirect_stdout(output):
        code = run_with_write_lock(root, namespace, argv, execute)
    return dict(status='saved' if saved is not None else 'queued' if code == 0 else 'busy',
                completed=saved is not None, record=saved, report=output.getvalue().strip(), exit_code=code)
