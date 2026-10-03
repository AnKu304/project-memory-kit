"""Explicit, recoverable retirement of native derived code projections."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import shutil
import uuid
from contextlib import closing
from pathlib import Path

from tools.project_memory.config import config_path, load_config
from tools.project_memory.graph.sqlite_store import SQLiteGraphStore
from tools.project_memory.services.code_provider import external_code, is_code_source
from tools.project_memory.services.concurrency import MemoryWriteLock, MemoryResourceLock
from tools.project_memory.vector.qdrant_store import QdrantLocalStore

DERIVED = ('File', 'Module', 'Symbol', 'Chunk', 'Route')
TABLES = ('knowledge_entries', 'knowledge_links', 'rationale_entries', 'rationale_links',
          'failure_fingerprints', 'changesets', 'command_runs')


def _durable_digest(connection):
    values = {table: [list(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY 1')]
              for table in TABLES}
    values['durable_nodes'] = [list(row) for row in connection.execute(
        "SELECT * FROM nodes WHERE kind NOT IN ('File','Module','Symbol','Chunk','Route') ORDER BY id")]
    values['durable_fts'] = [list(row) for row in connection.execute(
        "SELECT * FROM chunks_fts WHERE chunk_id IN (SELECT id FROM nodes WHERE kind != 'Chunk') ORDER BY chunk_id")]
    values['memory_edges'] = [list(row) for row in connection.execute(
        "SELECT e.* FROM edges e JOIN nodes s ON s.id=e.src_id JOIN nodes d ON d.id=e.dst_id "
        "WHERE s.kind IN ('Knowledge','KnowledgeChunk','Rationale','RationaleChunk','HumanNote','HumanChunk') "
        "OR d.kind IN ('Knowledge','KnowledgeChunk','Rationale','RationaleChunk','HumanNote','HumanChunk') ORDER BY e.id")]
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def _preview(connection, root):
    paths = [row[0] for row in connection.execute('SELECT path FROM file_index_state ORDER BY path') if is_code_source(root, row[0])]
    connection.execute('CREATE TEMP TABLE code_paths(path TEXT PRIMARY KEY)')
    connection.executemany('INSERT INTO code_paths VALUES (?)', [(p,) for p in paths])
    # Independently authored memory edges retain their source anchors. Code anchors
    # are metadata only; no parser/chunk/vector pipeline owns them after cutover.
    connection.execute("CREATE TEMP TABLE code_nodes AS SELECT id FROM nodes n WHERE path IN (SELECT path FROM code_paths) "
        "AND kind IN ('File','Module','Symbol','Chunk','Route') AND NOT EXISTS ("
        "SELECT 1 FROM edges e JOIN nodes other ON other.id=CASE WHEN e.src_id=n.id THEN e.dst_id ELSE e.src_id END "
        "WHERE (e.src_id=n.id OR e.dst_id=n.id) AND other.kind IN "
        "('Knowledge','KnowledgeChunk','Rationale','RationaleChunk','HumanNote','HumanChunk'))")
    counts = {row['kind']: row['n'] for row in connection.execute(
        'SELECT kind,count(*) n FROM nodes WHERE id IN (SELECT id FROM code_nodes) GROUP BY kind')}
    return {'mode': 'preview', 'code_paths': paths, 'nodes_by_kind': counts,
            'fts_chunks': connection.execute('SELECT count(*) FROM chunks_fts WHERE chunk_id IN (SELECT id FROM code_nodes)').fetchone()[0],
            'edges': connection.execute('SELECT count(*) FROM edges WHERE src_id IN (SELECT id FROM code_nodes) OR dst_id IN (SELECT id FROM code_nodes)').fetchone()[0],
            'durable_digest': _durable_digest(connection)}


def migrate_code(root: Path, *, apply=False):
    root = root.resolve()
    if not external_code(root):
        raise ValueError('Derived code migration requires explicit code_provider.backend=gitnexus')
    db = config_path(root, 'graph_db')
    db.resolve().relative_to(root)
    if not db.is_file() or db.is_symlink():
        raise ValueError('Migration requires an existing project-owned database')
    store = SQLiteGraphStore(root, db)
    if not apply:
        with closing(store.connect()) as connection:
            return _preview(connection, root)
    with MemoryWriteLock(root, 'retire native code index'):
        with closing(store.connect()) as connection:
            preview = _preview(connection, root)
            connection.commit()  # Preview temporary tables do not own the write transaction.
            if not preview['code_paths']:
                return {**preview, 'mode': 'applied', 'completed': True, 'backup': None,
                        'durable_digest_after': preview['durable_digest'], 'vector_status': 'already_migrated'}
            vectors_path = config_path(root, 'qdrant_path')
            vectors_path.resolve().relative_to(root)
            if any(p.is_symlink() for p in [vectors_path, *vectors_path.parents]):
                raise ValueError('Vector store symlinks are forbidden')
            if vectors_path.exists():
                for directory, directories, files in os.walk(vectors_path, followlinks=False):
                    if any((Path(directory) / name).is_symlink() for name in directories + files):
                        raise ValueError('Vector store contains symlinks; refusing cross-project backup')
            vector_cfg = load_config(root).get('vector', {})
            if vector_cfg.get('url'):
                raise ValueError('Remote vector migration requires a provider-side snapshot; local migration refuses unsafe cleanup')
            backup_dir = root / '.project-memory' / 'backups' / ('code-migration-' + uuid.uuid4().hex)
            if backup_dir.parent.is_symlink():
                raise ValueError('Migration backup directory must stay inside project')
            backup_dir.mkdir(parents=True)
            backup = backup_dir / 'graph.sqlite'
            with closing(sqlite3.connect(backup)) as saved:
                connection.backup(saved)
            with MemoryResourceLock(root, 'qdrant', 'back up vectors for code migration'):
                if vectors_path.exists():
                    shutil.copytree(vectors_path, backup_dir / 'vector-store')
            vectors = QdrantLocalStore(vectors_path, backend=vector_cfg.get('backend', 'auto'),
                collection=vector_cfg.get('collection', 'project_memory_chunks'),
                model_name=vector_cfg.get('embedding_model'), root=root, load_embeddings=False)
            doomed_chunks = {row[0] for row in connection.execute(
                "SELECT id FROM nodes WHERE kind='Chunk' AND id IN (SELECT id FROM code_nodes)")}
            connection.execute('BEGIN IMMEDIATE')
            try:
                connection.execute('DELETE FROM chunks_fts WHERE chunk_id IN (SELECT id FROM code_nodes)')
                connection.execute('DELETE FROM nodes WHERE id IN (SELECT id FROM code_nodes)')
                connection.execute('DELETE FROM file_index_state WHERE path IN (SELECT path FROM code_paths)')
                after = _durable_digest(connection)
                if after != preview['durable_digest']:
                    raise RuntimeError('Durable memory invariant changed; migration rolled back')
                if connection.execute('PRAGMA foreign_key_check').fetchall():
                    raise RuntimeError('Foreign key invariant failed; migration rolled back')
                removed_vectors = vectors.retire_chunks(doomed_chunks, code_paths=set(preview['code_paths']))
                connection.commit()
            except Exception as exc:
                connection.rollback()
                vectors.close()
                try:
                    with MemoryResourceLock(root, 'qdrant', 'restore vector migration backup'):
                        if vectors_path.exists():
                            os.replace(vectors_path, backup_dir / 'failed-vector-store')
                        if (backup_dir / 'vector-store').exists():
                            shutil.copytree(backup_dir / 'vector-store', vectors_path)
                except Exception as restore_error:
                    raise RuntimeError(f'Migration failed; SQLite rolled back, vector restoration pending. '
                                       f'Recover from {backup_dir}: {restore_error}') from exc
                raise RuntimeError(f'Migration rolled back including vectors; recoverable backup: {backup_dir}') from exc
            finally:
                vectors.close()
        vector_status = {'removed_fallback_vectors': removed_vectors, 'retired_chunk_ids': len(doomed_chunks),
                         'backend': vector_cfg.get('backend', 'auto'), 'backup': str(backup_dir / 'vector-store')}
        receipt = {**preview, 'mode': 'applied', 'backup': str(backup), 'durable_digest_after': after,
                   'vector_status': vector_status, 'completed': True}
        (backup_dir / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        return receipt
