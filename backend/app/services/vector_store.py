"""Qdrant: one collection of chunk vectors, searched one knowledge base at a time (§4.2).

Layout (D50):
- One collection (`QDRANT_COLLECTION`, default "chunks"), 384-dimensional, cosine distance.
- Point id = the chunk's id in PostgreSQL. PostgreSQL keeps the text; Qdrant keeps the vector and
  a small payload: kb_id, document_id, owner_id, chunk_index, pages, and the front-matter fields
  doc_code / doc_version / doc_status (S2) for filtering later.
- Payload indexes on every field we filter or delete by: kb_id (marked as the tenant key),
  owner_id, document_id, doc_status. Without one Qdrant would check every point's payload, and
  Qdrant Cloud's strict mode refuses such a filter outright (400 "Index required but not found",
  found in the M9 live tests; the in-memory client doesn't enforce it).
- Every search requires an owner id AND a knowledge base id: there is no way to call it unscoped.

Qdrant is not transactional with PostgreSQL, so the order of writes is what keeps them consistent
(pipeline.py, documents.py: ARCHITECTURE §4.11).
"""

from __future__ import annotations

import threading
import uuid
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import Settings

UPSERT_BATCH = 128  # points per request: ~128 x 384 floats ≈ 0.5 MB of JSON

# field -> index type. kb_id is the tenant key: Qdrant stores each tenant's points together.
PAYLOAD_INDEXES: dict[str, models.KeywordIndexParams] = {
    "kb_id": models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD, is_tenant=True),
    "owner_id": models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD),
    "document_id": models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD),
    "doc_status": models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD),
}


def build_qdrant_client(settings: Settings) -> QdrantClient:
    api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=api_key,
        timeout=30,
        # By default the client calls the server while being constructed, to compare versions.
        # That would put a network call (~260 ms) inside app startup and inside every test that
        # builds the app. pyproject pins the client to the server's minor version (1.20) instead.
        check_compatibility=False,
    )


class VectorStoreConfigError(RuntimeError):
    """The existing collection doesn't fit the embedding model (e.g. a different dimension)."""


@dataclass(frozen=True)
class ChunkPoint:
    id: uuid.UUID
    vector: list[float]
    payload: dict[str, Any]


@dataclass(frozen=True)
class SearchHit:
    chunk_id: uuid.UUID
    score: float  # cosine similarity, -1..1 (higher = closer)
    payload: dict[str, Any]


def _match(key: str, value: object) -> models.FieldCondition:
    return models.FieldCondition(key=key, match=models.MatchValue(value=str(value)))


def _is_missing_collection(exc: Exception) -> bool:
    # Server: HTTP 404. qdrant-client's in-memory mode (unit tests): ValueError "... not found".
    if isinstance(exc, UnexpectedResponse):
        return exc.status_code == 404
    return isinstance(exc, ValueError) and "not found" in str(exc)


class VectorStore:
    def __init__(self, client: QdrantClient, collection: str) -> None:
        self.client = client
        self.collection = collection
        self._ready_dimension: int | None = None
        self._lock = threading.Lock()

    # --- the collection --------------------------------------------------------------------

    def ensure_collection(self, dimension: int) -> bool:
        """Create the collection and its payload indexes if missing; check an existing one fits.
        Returns True if it was created. After the first success this costs nothing (no request).
        """
        with self._lock:
            if self._ready_dimension == dimension:
                return False
            created = False
            if not self.client.collection_exists(self.collection):
                try:
                    self.client.create_collection(
                        self.collection,
                        vectors_config=models.VectorParams(
                            size=dimension, distance=models.Distance.COSINE
                        ),
                    )
                    created = True
                except UnexpectedResponse as exc:
                    if exc.status_code != 409:  # 409: another process created it just now
                        raise
            info = self.client.get_collection(self.collection)
            params = info.config.params.vectors
            if not isinstance(params, models.VectorParams) or (
                params.size,
                params.distance,
            ) != (dimension, models.Distance.COSINE):
                raise VectorStoreConfigError(
                    f"Qdrant collection '{self.collection}' doesn't match the embedding model "
                    f"({dimension}-d cosine). Rebuild it with scripts/reindex.py."
                )
            existing = set((info.payload_schema or {}).keys())
            for field, schema in PAYLOAD_INDEXES.items():
                if field not in existing:
                    self.client.create_payload_index(
                        self.collection, field, field_schema=schema, wait=True
                    )
            self._ready_dimension = dimension
            return created

    def recreate(self, dimension: int) -> None:
        """Drop and create the collection empty (scripts/reindex.py only)."""
        with self._lock:
            if self.client.collection_exists(self.collection):
                self.client.delete_collection(self.collection)
            self._ready_dimension = None
        self.ensure_collection(dimension)

    # --- writes ----------------------------------------------------------------------------

    def upsert(self, points: Sequence[ChunkPoint]) -> None:
        """Insert or overwrite points, in batches. `wait=True`: when this returns, the points
        are stored and searchable, so "ready" in PostgreSQL never runs ahead of Qdrant."""
        for start in range(0, len(points), UPSERT_BATCH):
            batch = points[start : start + UPSERT_BATCH]
            self.client.upsert(
                self.collection,
                points=[
                    models.PointStruct(id=str(p.id), vector=p.vector, payload=p.payload)
                    for p in batch
                ],
                wait=True,
            )

    def _delete(self, conditions: models.Filter) -> None:
        try:
            self.client.delete(
                self.collection,
                points_selector=models.FilterSelector(filter=conditions),
                wait=True,
            )
        except Exception as exc:
            if not _is_missing_collection(exc):  # no collection = nothing to delete
                raise

    def delete_document(
        self, document_id: uuid.UUID, *, keep: Iterable[uuid.UUID] = ()
    ) -> None:
        """Remove a document's points, except the ids in `keep` (the fresh set, when a
        reprocessed document replaces its old points)."""
        keep_ids = [str(i) for i in keep]
        self._delete(
            models.Filter(
                must=[_match("document_id", document_id)],
                must_not=[models.HasIdCondition(has_id=keep_ids)] if keep_ids else None,
            )
        )

    def delete_knowledge_base(self, kb_id: uuid.UUID) -> None:
        self._delete(models.Filter(must=[_match("kb_id", kb_id)]))

    # --- reads -----------------------------------------------------------------------------

    def count(self, *, kb_id: uuid.UUID | None = None, document_id: uuid.UUID | None = None) -> int:
        conditions = [_match("kb_id", kb_id)] if kb_id else []
        if document_id:
            conditions.append(_match("document_id", document_id))
        try:
            return self.client.count(
                self.collection,
                count_filter=models.Filter(must=conditions) if conditions else None,
                exact=True,
            ).count
        except Exception as exc:
            if _is_missing_collection(exc):
                return 0
            raise

    def search(
        self,
        vector: list[float],
        *,
        owner_id: uuid.UUID,
        kb_id: uuid.UUID,
        limit: int,
        document_id: uuid.UUID | None = None,
    ) -> list[SearchHit]:
        """Nearest chunks within ONE knowledge base of ONE owner. The caller has already checked
        in PostgreSQL that `owner_id` owns `kb_id`; the owner filter is a second lock on the door.
        """
        conditions = [_match("owner_id", owner_id), _match("kb_id", kb_id)]
        if document_id:
            conditions.append(_match("document_id", document_id))
        response = self.client.query_points(
            self.collection,
            query=vector,
            query_filter=models.Filter(must=conditions),
            limit=limit,
            with_payload=True,
        )
        return [
            SearchHit(chunk_id=uuid.UUID(str(p.id)), score=p.score, payload=p.payload or {})
            for p in response.points
        ]

    def points_per_document(self) -> Counter[str]:
        """document_id -> number of points, for the whole collection (scripts/reindex.py --check).
        Scrolls payloads only, never vectors."""
        counts: Counter[str] = Counter()
        offset = None
        while True:
            try:
                points, offset = self.client.scroll(
                    self.collection,
                    limit=1000,
                    offset=offset,
                    with_payload=["document_id"],
                    with_vectors=False,
                )
            except Exception as exc:
                if _is_missing_collection(exc):
                    return counts
                raise
            counts.update(str((p.payload or {}).get("document_id")) for p in points)
            if offset is None:
                return counts
