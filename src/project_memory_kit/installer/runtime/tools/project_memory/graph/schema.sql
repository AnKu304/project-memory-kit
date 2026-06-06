PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  name TEXT,
  fqn TEXT,
  path TEXT,
  language TEXT,
  layer TEXT,
  start_line INTEGER,
  end_line INTEGER,
  hash TEXT,
  properties_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
CREATE INDEX IF NOT EXISTS idx_nodes_path ON nodes(path);
CREATE INDEX IF NOT EXISTS idx_nodes_fqn ON nodes(fqn);
CREATE INDEX IF NOT EXISTS idx_nodes_kind_path ON nodes(kind, path);

CREATE TABLE IF NOT EXISTS edges (
  id TEXT PRIMARY KEY,
  src_id TEXT NOT NULL,
  dst_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  source TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 1.0,
  evidence TEXT,
  properties_json TEXT NOT NULL DEFAULT '{}',
  stale INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(src_id) REFERENCES nodes(id) ON DELETE CASCADE,
  FOREIGN KEY(dst_id) REFERENCES nodes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src_id);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_id);
CREATE INDEX IF NOT EXISTS idx_edges_kind ON edges(kind);
CREATE INDEX IF NOT EXISTS idx_edges_src_kind ON edges(src_id, kind);
CREATE INDEX IF NOT EXISTS idx_edges_dst_kind ON edges(dst_id, kind);

CREATE TABLE IF NOT EXISTS file_index_state (
  path TEXT PRIMARY KEY,
  hash TEXT NOT NULL,
  indexed_at TEXT NOT NULL,
  parser TEXT,
  warnings_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS changesets (
  id TEXT PRIMARY KEY,
  base TEXT,
  head TEXT,
  summary TEXT,
  created_at TEXT NOT NULL,
  properties_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS command_runs (
  id TEXT PRIMARY KEY,
  command TEXT NOT NULL,
  exit_code INTEGER,
  log_path TEXT,
  created_at TEXT NOT NULL,
  properties_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS failure_fingerprints (
  fingerprint TEXT PRIMARY KEY,
  error_kind TEXT,
  normalized_message TEXT,
  top_project_frame TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 1,
  resolved_changeset TEXT,
  properties_json TEXT NOT NULL DEFAULT '{}'
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  chunk_id UNINDEXED,
  path UNINDEXED,
  fqn UNINDEXED,
  content
);

