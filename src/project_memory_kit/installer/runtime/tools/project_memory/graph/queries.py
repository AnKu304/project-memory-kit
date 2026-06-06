from __future__ import annotations

TOUCHED_SYMBOLS = """
SELECT id, name, fqn, path, start_line, end_line
FROM nodes
WHERE kind = 'Symbol'
  AND path = ?
  AND start_line <= ?
  AND end_line >= ?
ORDER BY start_line
"""

REVERSE_IMPORTS = """
SELECT DISTINCT n.path, n.fqn, e.evidence
FROM edges e
JOIN nodes n ON n.id = e.src_id
WHERE e.kind = 'IMPORTS' AND e.dst_id = ?
"""

CHUNKS_FOR_PATH = """
SELECT id, name, fqn, path, start_line, end_line, properties_json
FROM nodes
WHERE kind = 'Chunk' AND path = ?
ORDER BY start_line
"""

