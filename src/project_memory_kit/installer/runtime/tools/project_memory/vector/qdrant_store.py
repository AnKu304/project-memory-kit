from __future__ import annotations

from contextlib import contextmanager
import json
import hashlib
import os
import re
import tempfile
import uuid
from pathlib import Path

from tools.project_memory.services.concurrency import MemoryBusyError, MemoryResourceLock
from tools.project_memory.vector.embeddings import DeterministicEmbeddings, FastEmbedEmbeddings
from tools.project_memory.services.auto_index import request_resource


class VectorBackendBusyError(RuntimeError):
    """The embedded local vector backend is in use by another reader/writer."""


def _is_local_busy(error: Exception) -> bool:
    if isinstance(error, (MemoryBusyError, VectorBackendBusyError)):
        return True
    # Qdrant local uses RuntimeError for its own storage lock. Match that
    # specific message, not unrelated corruption/configuration/busy errors.
    return isinstance(error, RuntimeError) and bool(re.fullmatch(
        r"Storage folder .+ is already accessed by another instance of Qdrant client\."
        r"(?: If you require concurrent access, use Qdrant server instead\.)?",
        str(error),
    ))


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
        self._local = not bool(url)
        self._local_busy = False
        self._query_cache = None
        self._request_root = root or self.path.parent.parent
        self._model_name = model_name
        self._lock: MemoryResourceLock | None = None
        self._collection_ready = False
        self._fallback_batch_limit = 0
        self._fallback_pending: dict[str, str] = {}
        self._fallback_pending_bytes = 0
        if backend != "fallback":
            try:
                from qdrant_client import QdrantClient

                if not url:
                    lock_root = root or self.path.parent.parent
                    self._lock = MemoryResourceLock(lock_root, "qdrant", "qdrant local access")
                    self._lock.__enter__()
                self.client = QdrantClient(url=url) if url else QdrantClient(path=str(self.path))
                self.embeddings = request_resource(
                    self._request_root, ('embedder', model_name),
                    lambda: FastEmbedEmbeddings(model_name=model_name),
                )
                self.backend = "qdrant"
            except Exception as exc:
                self.close()
                self._local_busy = self._local and _is_local_busy(exc)
                if self.strict_qdrant:
                    if self._local_busy:
                        raise VectorBackendBusyError("qdrant local vector backend is busy") from exc
                    raise RuntimeError("qdrant vector backend requested but unavailable") from exc
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

    def _raise_if_local_busy(self, error: Exception) -> None:
        if self._local and _is_local_busy(error):
            raise VectorBackendBusyError("qdrant local vector backend is busy") from error

    @contextmanager
    def query_session(self):
        """Reuse one query embedding only during this caller-owned operation."""
        previous = self._query_cache
        self._query_cache = {}
        try:
            yield self
        finally:
            self._query_cache = previous

    def _embed_query(self, query):
        def embed():
            return request_resource(
                self._request_root, ('query', self.backend, self.vector_size, self._model_name,
                                     hashlib.sha256(query.encode()).hexdigest()),
                lambda: tuple(self.embeddings.embed(query)),
            )
        if self._query_cache is None:
            return list(embed())
        if query not in self._query_cache:
            self._query_cache.clear()
            self._query_cache[query] = embed()
        return list(self._query_cache[query])

    def search(self, query: str, limit: int = 10, *, query_filter=None) -> list[dict[str, object]]:
        if self._local_busy:
            raise VectorBackendBusyError("qdrant local vector backend is busy")
        if self.backend != "qdrant" or self.client is None:
            return []
        try:
            if not self.client.collection_exists(self.collection):
                return []
            vector = self._embed_query(query)
        except Exception as exc:
            self._raise_if_local_busy(exc)
            if self.strict_qdrant:
                raise RuntimeError("qdrant vector search failed") from exc
            return []
        if isinstance(query_filter, dict):
            from qdrant_client.models import Filter
            query_filter = Filter(**query_filter)
        filter_args = {"query_filter": query_filter} if query_filter is not None else {}
        try:
            result = self.client.query_points(
                collection_name=self.collection,
                query=vector,
                limit=limit,
                with_payload=True,
                **filter_args,
            )
            points = getattr(result, "points", result)
        except (AttributeError, TypeError):
            try:
                points = self.client.search(
                    collection_name=self.collection,
                    query_vector=vector,
                    limit=limit,
                    with_payload=True,
                    **filter_args,
                )
            except Exception as exc:
                self._raise_if_local_busy(exc)
                raise
        except Exception as exc:
            self._raise_if_local_busy(exc)
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

    @contextmanager
    def batch_fallback(self, max_chunks: int = 128):
        """Batch fallback writes inside the caller's existing project write lock.

        Qdrant operations remain immediate. Flush completed chunks even when a
        later operation fails; this is a write batch, not a rollback transaction.
        """
        if max_chunks < 1:
            raise ValueError("max_chunks must be positive")
        if self._fallback_batch_limit:
            raise RuntimeError("fallback batches cannot be nested")
        self._fallback_batch_limit = max_chunks
        try:
            yield self
        finally:
            self._fallback_batch_limit = 0
            self._flush_fallback()

    def _upsert_fallback(self, chunk_id: str, vector: list[float], payload: dict[str, object]) -> None:
        row = json.dumps({"id": chunk_id, "vector": vector, "payload": payload}, sort_keys=True) + "\n"
        # Bound pending serialized data as well as row count. An individual large
        # row is still supported and is flushed immediately.
        row_bytes = len(row.encode("utf-8"))
        if self._fallback_pending_bytes + row_bytes > 1024 * 1024:
            self._flush_fallback()
        previous = self._fallback_pending.pop(chunk_id, "")
        self._fallback_pending_bytes -= len(previous.encode("utf-8"))
        self._fallback_pending[chunk_id] = row
        self._fallback_pending_bytes += row_bytes
        if (
            not self._fallback_batch_limit
            or len(self._fallback_pending) >= self._fallback_batch_limit
            or self._fallback_pending_bytes >= 1024 * 1024
        ):
            self._flush_fallback()

    def _flush_fallback(self) -> None:
        if not self._fallback_pending:
            return
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path,
                prefix=".fallback_chunks-", suffix=".tmp", delete=False,
            ) as output:
                temporary = Path(output.name)
                if self.fallback_file.exists():
                    with self.fallback_file.open(encoding="utf-8") as source:
                        for line in source:
                            if not line.strip():
                                continue
                            item = json.loads(line)
                            if item.get("id") not in self._fallback_pending:
                                output.write(line if line.endswith("\n") else line + "\n")
                for row in self._fallback_pending.values():
                    output.write(row)
            os.replace(temporary, self.fallback_file)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self._fallback_pending.clear()
        self._fallback_pending_bytes = 0
