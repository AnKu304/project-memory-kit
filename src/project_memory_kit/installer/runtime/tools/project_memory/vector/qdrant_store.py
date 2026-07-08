from __future__ import annotations

import json
import uuid
from pathlib import Path

from tools.project_memory.services.concurrency import MemoryBusyError, MemoryResourceLock
from tools.project_memory.vector.embeddings import DeterministicEmbeddings, FastEmbedEmbeddings


def _normalize_backend(backend: str | None) -> str:
    value = (backend or "auto").lower()
    return value if value in {"auto", "qdrant", "fallback"} else "auto"


def vector_backend_status(backend: str | None = "auto", url: str | None = None) -> str:
    backend = _normalize_backend(backend)
    if backend == "fallback":
        return "deterministic fallback (configured)"
    missing: list[str] = []
    try:
        import qdrant_client  # noqa: F401
    except Exception:
        missing.append("qdrant-client")
    try:
        import fastembed  # noqa: F401
    except Exception:
        missing.append("fastembed")
    if missing:
        if backend == "qdrant":
            return "qdrant requested but unavailable (missing " + ", ".join(missing) + ")"
        return "deterministic fallback (missing " + ", ".join(missing) + ")"
    return "qdrant server + fastembed available" if url else "qdrant local + fastembed available (guarded)"


class QdrantLocalStore:
    def __init__(
        self,
        path: Path,
        vector_size: int = 64,
        backend: str = "auto",
        collection: str = "project_memory_chunks",
        model_name: str | None = None,
        url: str | None = None,
        root: Path | None = None,
    ):
        backend = _normalize_backend(backend)
        self.path = path
        self.path.mkdir(parents=True, exist_ok=True)
        self.fallback_file = self.path / "fallback_chunks.jsonl"
        self.collection = collection
        self.vector_size = vector_size
        self.strict_qdrant = backend == "qdrant"
        self.backend = "fallback"
        self.client = None
        self._lock: MemoryResourceLock | None = None
        self._collection_ready = False
        if backend != "fallback":
            try:
                from qdrant_client import QdrantClient

                if not url:
                    lock_root = root or self.path.parent.parent
                    self._lock = MemoryResourceLock(lock_root, "qdrant", "qdrant local access")
                    self._lock.__enter__()
                self.client = QdrantClient(url=url) if url else QdrantClient(path=str(self.path))
                self.embeddings = FastEmbedEmbeddings(model_name=model_name)
                self.backend = "qdrant"
            except MemoryBusyError as exc:
                self._release_lock()
                if self.strict_qdrant:
                    raise RuntimeError("qdrant local vector backend is busy") from exc
                self.client = None
                self.embeddings = DeterministicEmbeddings(vector_size)
            except Exception as exc:
                self._release_lock()
                if self.strict_qdrant:
                    raise RuntimeError("qdrant vector backend requested but unavailable") from exc
                self.client = None
                self.embeddings = DeterministicEmbeddings(vector_size)
        else:
            self.embeddings = DeterministicEmbeddings(vector_size)

    def _release_lock(self) -> None:
        if self._lock is not None:
            self._lock.__exit__(None, None, None)
            self._lock = None

    def close(self) -> None:
        client = self.client
        self.client = None
        if client is not None and hasattr(client, "close"):
            try:
                client.close()
            except Exception:
                pass
        self._release_lock()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def upsert_chunk(self, chunk_id: str, text: str, payload: dict[str, object]) -> None:
        try:
            vector = self.embeddings.embed(text)
            if self.backend == "qdrant" and self.client is not None:
                self._upsert_qdrant(chunk_id, vector, payload)
                return
        except Exception as exc:
            if self.strict_qdrant:
                raise RuntimeError(f"qdrant vector upsert failed for {chunk_id}") from exc
            vector = DeterministicEmbeddings(self.vector_size).embed(text)
        self._upsert_fallback(chunk_id, vector, payload)

    def _upsert_qdrant(self, chunk_id: str, vector: list[float], payload: dict[str, object]) -> None:
        from qdrant_client.models import Distance, PointStruct, VectorParams

        if not self._collection_ready:
            if not self.client.collection_exists(self.collection):
                self.client.create_collection(
                    collection_name=self.collection,
                    vectors_config=VectorParams(size=len(vector), distance=Distance.COSINE),
                )
            self._collection_ready = True
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))
        self.client.upsert(
            collection_name=self.collection,
            wait=True,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={**payload, "chunk_id": chunk_id, "point_id": point_id},
                )
            ],
        )

    def search(self, query: str, limit: int = 10) -> list[dict[str, object]]:
        if self.backend != "qdrant" or self.client is None:
            return []
        try:
            if not self.client.collection_exists(self.collection):
                return []
            vector = self.embeddings.embed(query)
        except Exception as exc:
            if self.strict_qdrant:
                raise RuntimeError("qdrant vector search failed") from exc
            return []
        try:
            result = self.client.query_points(
                collection_name=self.collection,
                query=vector,
                limit=limit,
                with_payload=True,
            )
            points = getattr(result, "points", result)
        except (AttributeError, TypeError):
            points = self.client.search(
                collection_name=self.collection,
                query_vector=vector,
                limit=limit,
                with_payload=True,
            )
        except Exception as exc:
            if self.strict_qdrant:
                raise RuntimeError("qdrant vector search failed") from exc
            return []

        hits: list[dict[str, object]] = []
        for point in points:
            payload = dict(getattr(point, "payload", None) or {})
            chunk_id = payload.get("chunk_id")
            if chunk_id:
                hits.append(
                    {
                        "chunk_id": str(chunk_id),
                        "score": float(getattr(point, "score", 0.0) or 0.0),
                        "payload": payload,
                    }
                )
        return hits

    def _upsert_fallback(self, chunk_id: str, vector: list[float], payload: dict[str, object]) -> None:
        row = {"id": chunk_id, "vector": vector, "payload": payload}
        existing = []
        if self.fallback_file.exists():
            for line in self.fallback_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                if item.get("id") != chunk_id:
                    existing.append(item)
        existing.append(row)
        self.fallback_file.write_text(
            "\n".join(json.dumps(item, sort_keys=True) for item in existing) + "\n",
            encoding="utf-8",
        )
