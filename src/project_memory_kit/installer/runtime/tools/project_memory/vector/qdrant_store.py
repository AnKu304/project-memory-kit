from __future__ import annotations

import json
from pathlib import Path

from tools.project_memory.vector.embeddings import DeterministicEmbeddings


class QdrantLocalStore:
    """Small local-vector facade.

    The runtime writes deterministic vectors to disk even when qdrant-client or
    FastEmbed are not installed yet. This keeps `pmem` usable immediately after
    bootstrap while preserving the Qdrant local storage boundary.
    """

    def __init__(self, path: Path, vector_size: int = 64):
        self.path = path
        self.path.mkdir(parents=True, exist_ok=True)
        self.file = self.path / "chunks.jsonl"
        self.embeddings = DeterministicEmbeddings(vector_size)

    def upsert_chunk(self, chunk_id: str, text: str, payload: dict[str, object]) -> None:
        row = {"id": chunk_id, "vector": self.embeddings.embed(text), "payload": payload}
        existing = []
        if self.file.exists():
            for line in self.file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                if item.get("id") != chunk_id:
                    existing.append(item)
        existing.append(row)
        self.file.write_text("\n".join(json.dumps(item, sort_keys=True) for item in existing) + "\n", encoding="utf-8")

