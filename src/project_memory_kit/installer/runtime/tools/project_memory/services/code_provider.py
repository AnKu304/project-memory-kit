"""Read-only GitNexus bridge. Configured projects are capabilities, not search hints."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

from tools.project_memory.config import load_config

CODE_EXTENSIONS = frozenset({'.py', '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.mts', '.cts',
    '.php', '.rb', '.go', '.rs', '.java', '.kt', '.kts', '.swift', '.c', '.h', '.cpp', '.hpp',
    '.cs', '.vue', '.svelte', '.scala', '.sh', '.bash', '.sql', '.ex', '.exs', '.erl', '.lua',
    '.html', '.htm', '.css', '.scss', '.sass', '.less'})
MAX_OUTPUT = 1024 * 1024


def external_code(root: Path, cfg=None) -> bool:
    backend = (cfg or load_config(root)).get('code_provider', {}).get('backend', 'native')
    if backend not in {'native', 'gitnexus'}:
        raise ValueError('code_provider.backend must be native or gitnexus')
    return backend == 'gitnexus'


def is_code_path(path) -> bool:
    return Path(path).suffix.lower() in CODE_EXTENSIONS


def is_code_source(root, path, cfg=None):
    """Code/config ownership is explicit; ordinary text documents stay in PMEM."""
    cfg = cfg or load_config(root)
    extension = Path(path).suffix.lower()
    if extension in cfg.get('code_provider', {}).get('document_extensions', []):
        return False
    if extension not in CODE_EXTENSIONS | {'.json', '.yaml', '.yml', '.toml', '.xml'}:
        return False
    candidate = Path(path) if Path(path).is_absolute() else root / path
    for repository in cfg.get('code_provider', {}).get('repositories', []):
        rel = _relative(repository.get('path'), 'Repository path', allow_dot=True)
        try:
            candidate.resolve().relative_to((root / rel).resolve())
            return True
        except ValueError:
            pass
    return False


def _relative(value, label, allow_dot=False):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError(f'{label} must be a repository-relative path')
    path = Path(value)
    if path.is_absolute() or '..' in path.parts or (not allow_dot and value == '.'):
        raise ValueError(f'{label} must stay inside its repository')
    return path


def configured_repository(root, repository_id=None):
    root = root.resolve()
    cfg = load_config(root).get('code_provider', {})
    if not external_code(root):
        raise ValueError('GitNexus provider is not configured')
    entries = cfg.get('repositories', [])
    if not isinstance(entries, list) or not entries:
        raise ValueError('No explicit code repositories configured')
    ids, paths, selected = set(), set(), []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'id', 'path', 'name'}:
            raise ValueError('Repository requires exact id, path, name fields')
        identity = entry['id']
        if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', identity):
            raise ValueError('Invalid repository identity')
        if not isinstance(entry['name'], str) or not 1 <= len(entry['name']) <= 256 or '\0' in entry['name']:
            raise ValueError('Invalid registered repository name')
        rel = _relative(entry['path'], 'Repository path', allow_dot=True)
        unresolved = root / rel
        if any(part.is_symlink() for part in [unresolved, *unresolved.parents] if part != root.parent):
            raise ValueError('Code repository symlinks are forbidden')
        repo = unresolved.resolve()
        repo.relative_to(root)
        if not repo.is_dir():
            raise ValueError('Configured code repository is not an existing directory')
        if identity in ids or repo in paths:
            raise ValueError('Duplicate code repository identity/path')
        ids.add(identity); paths.add(repo)
        if repository_id is None or repository_id == identity:
            selected.append({**entry, 'root': repo})
    if len(selected) != 1:
        raise ValueError('Select one explicit configured repository id')
    return cfg, selected[0]


def _json_file(path):
    if path.is_symlink() or path.stat().st_size > MAX_OUTPUT:
        raise ValueError('Provider metadata must be a bounded regular file')
    return json.loads(path.read_text(encoding='utf-8'))


def provider_status(root: Path, repository_id=None):
    result = {'provider': 'gitnexus', 'status': 'unavailable', 'diagnostics': []}
    try:
        cfg, repo = configured_repository(root, repository_id)
        result.update(repository_id=repo['id'], repository_root=str(repo['root']), repository_name=repo['name'])
        registry_path = Path(cfg.get('registry_path', ''))
        if not registry_path.is_absolute():
            raise ValueError('GitNexus registry_path must be absolute')
        registry = _json_file(registry_path)
        if not isinstance(registry, list):
            raise ValueError('Invalid GitNexus repository registry')
        matches = [item for item in registry if isinstance(item, dict) and item.get('name') == repo['name']
                   and Path(item.get('path', '')).resolve() == repo['root']]
        if len(matches) != 1:
            raise ValueError('Repository registration missing or ambiguous; no implicit repository selection')
        item = matches[0]
        storage = Path(item.get('storagePath', ''))
        if not storage.is_absolute() or storage.is_symlink():
            raise ValueError('GitNexus index storage must be an absolute non-symlink directory')
        storage = storage.resolve()
        if cfg.get('storage_root'):
            allowed_storage = Path(cfg['storage_root'])
            if not allowed_storage.is_absolute():
                raise ValueError('GitNexus storage_root must be absolute')
            if allowed_storage.is_symlink():
                raise ValueError('GitNexus storage_root symlinks are forbidden')
            storage.relative_to(allowed_storage.resolve())
            if any(p.is_symlink() for p in Path(item['storagePath']).parents
                   if p != allowed_storage and p.is_relative_to(allowed_storage)):
                raise ValueError('GitNexus index storage symlink escape')
        elif storage != repo['root'] / '.gitnexus':
            raise ValueError('External index storage requires explicit code_provider.storage_root')
        meta = _json_file(storage / 'meta.json')
        if Path(meta.get('repoPath', '')).resolve() != repo['root']:
            raise ValueError('GitNexus index repository mismatch')
        if meta.get('indexedAt') != item.get('indexedAt') or meta.get('lastCommit') != item.get('lastCommit'):
            raise ValueError('GitNexus registry/index snapshot mismatch')
        indexed_at = datetime.fromisoformat(meta['indexedAt'].replace('Z', '+00:00')).timestamp()
        revision = meta.get('lastCommit') or ('snapshot:' + hashlib.sha256(
            (str(repo['root']) + meta['indexedAt']).encode()).hexdigest())
        result.update(status='current', revision=revision, indexed_at=meta['indexedAt'],
                      provider_version=meta.get('runnerIdentity', {}).get('cliVersion'),
                      capabilities=['search', 'context', 'impact', 'changes', 'resolve'])
        if not (repo['root'] / '.git').exists():
            result.update(status='unknown', diagnostics=['Non-Git source freshness requires explicit reindex verification; index snapshot is available.'])
            return result
        head = subprocess.run(['git', '-C', str(repo['root']), 'rev-parse', 'HEAD'], capture_output=True,
                              text=True, timeout=5, check=True).stdout.strip()
        if head != revision:
            result['diagnostics'].append('Git HEAD differs from indexed revision')
        # This check never parses, hashes or indexes code; new/dirty source content is
        # distinguished from the snapshot using tracked diff paths and mtimes.
        dirty = subprocess.run(['git', '-C', str(repo['root']), 'status', '--porcelain', '-z'],
                               capture_output=True, timeout=5, check=True).stdout.decode('utf-8', 'replace')
        records = dirty.split('\0')
        if len(dirty.encode()) > MAX_OUTPUT:
            result['diagnostics'].append('Git dirty path inventory exceeds bound; freshness unknown')
        for record in records[:200]:
            if len(record) < 4:
                continue
            path = repo['root'] / record[3:]
            if record[:2].strip() in {'D', 'R', 'C'}:
                result['diagnostics'].append('Working tree contains deleted/renamed paths; snapshot requires verification')
                break
            if is_code_source(root, path) and path.is_file() and path.stat().st_mtime > indexed_at:
                result['diagnostics'].append('Source files changed after GitNexus indexed_at')
                break
        if len(records) > 200:
            result['diagnostics'].append('Dirty paths exceed freshness sample bound; inspect actual changes')
        if result['diagnostics']:
            result['status'] = 'stale'
    except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        result['diagnostics'].append(str(exc))
    return result


def _run(cfg, repo, arguments):
    command = cfg.get('command')
    if (not isinstance(command, list) or len(command) != 1 or not isinstance(command[0], str)
            or not Path(command[0]).is_absolute() or not os.access(command[0], os.X_OK)):
        raise ValueError('code_provider.command must contain one absolute executable path')
    timeout = max(1, min(float(cfg.get('timeout_seconds', 30)), 60))
    environment = {**os.environ, 'GITNEXUS_HOME': str(Path(cfg['registry_path']).parent),
                   'GITNEXUS_NO_UPDATE_NOTIFIER': '1', 'SCARF_ANALYTICS': 'false'}
    # File capture bounds RAM and output reads. Fixed read-only verbs, shell=False;
    # never pass arbitrary flags/commands from task content or stored references.
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(command + arguments + ['--repo', str(repo['root'])], cwd=repo['root'],
                                   stdout=output, stderr=output, env=environment, shell=False)
        try:
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                if output.tell() > MAX_OUTPUT:
                    raise ValueError('GitNexus output exceeded 1 MiB bound')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    process.wait(timeout=min(0.05, remaining))
                except subprocess.TimeoutExpired:
                    continue
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
            raise
        except ValueError:
            process.kill(); process.wait()
            raise
        if output.tell() > MAX_OUTPUT:
            raise ValueError('GitNexus output exceeded 1 MiB bound')
        output.seek(0)
        content = output.read(MAX_OUTPUT).decode('utf-8', 'replace')
    # GitNexus emits optional model-loading JSON log objects before the result.
    # Decode the bounded stream, accepting the last data object, never log text.
    decoder = json.JSONDecoder()
    candidates = []
    offset = 0
    while offset < len(content):
        positions = [p for p in (content.find('{', offset), content.find('[', offset)) if p >= 0]
        if not positions:
            break
        start = min(positions)
        try:
            item, end = decoder.raw_decode(content[start:])
        except json.JSONDecodeError:
            offset = start + 1
            continue
        offset = start + end
        if isinstance(item, (dict, list)) and not (isinstance(item, dict) and {'level', 'msg'} <= set(item)):
            candidates.append(item)
    if not candidates:
        raise ValueError('GitNexus returned no JSON evidence')
    evidence = candidates[-1]
    if process.returncode and not (isinstance(evidence, dict) and isinstance(evidence.get('error'), str)):
        raise RuntimeError('GitNexus read failed: ' + content[:1000])
    return evidence


def code_query(root: Path, operation='status', *, repository_id=None, query='', path=None, limit=5, base='HEAD'):
    if operation not in {'status', 'search', 'context', 'impact', 'changes', 'resolve'}:
        raise ValueError('Unsupported read-only code operation')
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError('Code query limit must be 1..20')
    if not isinstance(query, str) or len(query) > 4096 or query.startswith('-'):
        raise ValueError('Invalid bounded code query')
    if operation in {'search', 'context', 'resolve', 'impact'} and not query.strip():
        raise ValueError('Code query/symbol is required for this operation')
    if not isinstance(base, str) or len(base) > 256 or base.startswith('-'):
        raise ValueError('Invalid Git base reference')
    if path is not None:
        _relative(path, 'Symbol path')
    result = provider_status(root, repository_id)
    if operation == 'status' or result['status'] == 'unavailable':
        return result
    cfg, repo = configured_repository(root, repository_id)
    args = {'search': ['query', '--query', query, '--limit', str(limit)],
            'context': ['context', query, '--limit', str(limit)],
            'resolve': ['context', query, '--limit', str(limit)],
            'impact': ['impact', query, '--limit', str(limit), '--depth', '3'],
            'changes': ['detect-changes', '--scope', 'compare', '--base-ref', base, '--limit', str(limit)]}[operation]
    if path is not None and operation in {'context', 'impact', 'resolve'}:
        resolved = (repo['root'] / path).resolve()
        resolved.relative_to(repo['root'])
        args.extend(['--file', path])
    try:
        result['evidence'] = _run(cfg, repo, args)
        evidence = result['evidence']
        if isinstance(evidence, dict) and evidence.get('error'):
            message = str(evidence['error'])
            result['status'] = ('missing' if operation in {'context', 'resolve', 'impact'} and 'not found' in message.lower()
                                else 'unavailable')
            result['diagnostics'].append(message)
    except subprocess.TimeoutExpired:
        result.update(status='timeout', diagnostics=[*result['diagnostics'], 'GitNexus read timed out'])
    except (OSError, ValueError, RuntimeError) as exc:
        result.update(status='unavailable', diagnostics=[*result['diagnostics'], str(exc)])
    return result


def validate_code_reference(root, reference):
    required = {'schema_version', 'provider', 'repository_id', 'path', 'revision'}
    if (not isinstance(reference, dict) or not required <= set(reference)
            or set(reference) - required - {'symbol', 'symbol_id', 'content_hash'}):
        raise ValueError('Invalid versioned code reference fields')
    if type(reference['schema_version']) is not int or reference['schema_version'] != 1 or reference['provider'] != 'gitnexus':
        raise ValueError('Unsupported code reference schema/provider')
    _, repo = configured_repository(root, reference['repository_id'])
    path = _relative(reference['path'], 'Code reference path')
    (repo['root'] / path).resolve().relative_to(repo['root'])
    if not isinstance(reference['revision'], str) or not re.fullmatch(r'(?:[0-9a-f]{40,64}|snapshot:[0-9a-f]{64})', reference['revision']):
        raise ValueError('Code reference revision must be a Git commit hash or versioned snapshot hash')
    for key in ('symbol', 'symbol_id'):
        if key in reference and (not isinstance(reference[key], str) or not 1 <= len(reference[key]) <= 1024):
            raise ValueError('Invalid bounded code symbol locator')
    if 'content_hash' in reference and not re.fullmatch(r'[0-9a-f]{64}', str(reference['content_hash'])):
        raise ValueError('Code content_hash must be SHA-256')
    return dict(reference)


def resolve_code_reference(root, reference):
    reference = validate_code_reference(root, reference)
    status = provider_status(root, reference['repository_id'])
    if status['status'] == 'unavailable':
        return {**status, 'reference_status': 'unavailable'}
    _, repo = configured_repository(root, reference['repository_id'])
    path = repo['root'] / reference['path']
    if not path.is_file():
        return {**status, 'reference_status': 'missing'}
    stale = reference['revision'] != status.get('revision') or status['status'] != 'current'
    if reference.get('content_hash'):
        stale = stale or hashlib.sha256(path.read_bytes()).hexdigest() != reference['content_hash']
    if reference.get('symbol'):
        found = code_query(root, 'resolve', repository_id=reference['repository_id'],
                           query=reference['symbol'], path=reference['path'], limit=1)
        if 'evidence' not in found:
            return {**found, 'reference_status': 'unavailable'}
        evidence = found['evidence']
        if found['status'] in {'missing', 'unavailable', 'timeout'}:
            return {**found, 'reference_status': found['status']}
        if isinstance(evidence, dict) and evidence.get('status') == 'ambiguous':
            return {**found, 'reference_status': 'ambiguous'}
        symbol = evidence.get('symbol', {}) if isinstance(evidence, dict) else {}
        if (not isinstance(evidence, dict) or evidence.get('status') != 'found'
                or not isinstance(symbol, dict) or symbol.get('name') != reference['symbol']
                or symbol.get('filePath') != reference['path']):
            return {**found, 'reference_status': 'unresolved'}
    return {**status, 'reference_status': 'stale' if stale else 'current'}
