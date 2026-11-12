"""The background ingestion job and the document status lifecycle (ARCHITECTURE §3.1, §4.10, §4.11).

    uploaded --claim--> processing --> ready  --reprocess--> uploaded
                                   \\-> failed --reprocess--> uploaded
    (any) --delete--> deleting --> row removed

Steps: claim -> extract -> chunk -> embed (no database connection held for any of these) ->
index in Qdrant -> one PostgreSQL transaction (mark ready + replace the chunks).

Rules:
- Each status change is a conditional UPDATE ("... WHERE status = 'processing'"), so a job never
  overwrites a document that was deleted, retried or claimed by someone else meanwhile.
- `ready` is written only after Qdrant has confirmed the points (D51): a ready document always
  has its vectors. If the document vanished meanwhile (deleted), the job removes the points it
  just wrote, so it can't leave orphans behind.
- The job never raises: every outcome ends in `ready` or `failed` with a readable message, and
  unexpected errors are logged with their traceback.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Chunk, Document, KnowledgeBase
from app.services.embeddings import get_embedder
from app.services.ingestion.base import Extraction, ExtractionError
from app.services.ingestion.chunking import ChunkDraft, chunk_document
from app.services.ingestion.extractors import extract
from app.services.ingestion.tokens import get_tokens
from app.services.storage import Storage
from app.services.vector_store import ChunkPoint, VectorStore

logger = logging.getLogger("app.ingestion")

SessionFactory = Callable[[], Session]

UNEXPECTED = (
    "Something went wrong while processing this file. Try again; if it keeps failing, the file "
    "may be damaged."
)
INTERRUPTED = "Processing was interrupted because the server restarted. Please retry."
MISSING_FILE = "The stored file is missing. Delete this document and upload it again."
INDEX_UNAVAILABLE = (
    "The search index couldn't be updated (the vector database didn't respond). Please retry."
)

# Front-matter fields copied into each point's payload (S2), renamed so they can't be confused
# with our own ids: front matter's "document_id" is a policy code such as "NX-HR-002".
_PAYLOAD_METADATA = {"document_id": "doc_code", "version": "doc_version", "status": "doc_status"}


@dataclass(frozen=True)
class IngestionConfig:
    """What the job needs from Settings (kept small so scripts and tests can build one)."""

    embedding_model: str
    strategy: str = "auto"
    size: int = 400
    overlap: int = 60

    @classmethod
    def from_settings(cls, settings: Settings) -> IngestionConfig:
        return cls(
            embedding_model=settings.embedding_model,
            strategy=settings.chunk_strategy,
            size=settings.chunk_size_tokens,
            overlap=settings.chunk_overlap_tokens,
        )


def process_document(
    session_factory: SessionFactory,
    storage: Storage,
    vectors: VectorStore,
    config: IngestionConfig,
    document_id: uuid.UUID,
) -> None:
    try:
        _process(session_factory, storage, vectors, config, document_id)
    except Exception:  # noqa: BLE001 - a background job must not crash silently
        logger.exception("Ingestion job for document %s crashed", document_id)


def chunk_rows(drafts: list[ChunkDraft], document_id: uuid.UUID, kb_id: uuid.UUID) -> list[dict]:
    return [
        {
            # Generated here, not by the database: the chunk id is also its Qdrant point id.
            "id": uuid.uuid4(),
            "document_id": document_id,
            "kb_id": kb_id,
            "chunk_index": d.index,
            "text": d.text,
            "page_start": d.page_start,
            "page_end": d.page_end,
            "section": d.section,
            "token_count": d.token_count,
            "strategy": d.strategy,
        }
        for d in drafts
    ]


def point_payload(
    chunk: dict[str, Any] | Chunk, owner_id: uuid.UUID, metadata: dict[str, Any]
) -> dict[str, Any]:
    """The small payload stored next to each vector (no text: PostgreSQL has it)."""
    get = chunk.get if isinstance(chunk, dict) else lambda key: getattr(chunk, key)
    payload: dict[str, Any] = {
        "kb_id": str(get("kb_id")),
        "document_id": str(get("document_id")),
        "owner_id": str(owner_id),
        "chunk_index": get("chunk_index"),
        "page_start": get("page_start"),
        "page_end": get("page_end"),
    }
    for source, target in _PAYLOAD_METADATA.items():
        if metadata.get(source) is not None:
            payload[target] = str(metadata[source])
    return payload


def _process(
    session_factory: SessionFactory,
    storage: Storage,
    vectors: VectorStore,
    config: IngestionConfig,
    document_id: uuid.UUID,
) -> None:
    owner = (
        select(KnowledgeBase.owner_id)
        .where(KnowledgeBase.id == Document.kb_id)
        .scalar_subquery()
    )
    with session_factory() as db:
        claimed = db.execute(
            update(Document)
            .where(Document.id == document_id, Document.status == "uploaded")
            .values(status="processing", error_message=None)
            .returning(Document.stored_path, Document.file_type, Document.kb_id, owner)
        ).one_or_none()
        db.commit()
    if claimed is None:
        logger.info("Document %s is no longer waiting (deleted or claimed); skipping", document_id)
        return
    stored_path, file_type, kb_id, owner_id = claimed

    # CPU work, with no database connection held.
    timings: dict[str, float] = {}
    started = time.perf_counter()
    try:
        extraction = extract(storage.path_of(stored_path), file_type)
        drafts = chunk_document(
            extraction.blocks,
            extraction.metadata,
            get_tokens(config.embedding_model),
            strategy=config.strategy,
            size=config.size,
            overlap=config.overlap,
        )
        timings["parse+chunk"] = time.perf_counter() - started
        embedder = get_embedder(config.embedding_model)
        rows = chunk_rows(drafts, document_id, kb_id)
        embedded = embedder.embed_documents([row["text"] for row in rows])
        timings["embed"] = time.perf_counter() - started - timings["parse+chunk"]
    except ExtractionError as exc:
        _fail(session_factory, vectors, document_id, exc.message)
        logger.info("Document %s failed: %s", document_id, exc.message)
        return
    except FileNotFoundError:
        _fail(session_factory, vectors, document_id, MISSING_FILE)
        return
    except Exception:  # noqa: BLE001 - parsers can fail in unforeseen ways on odd files
        logger.exception("Processing of document %s raised an unexpected error", document_id)
        _fail(session_factory, vectors, document_id, UNEXPECTED)
        return

    # Index: new points first, then remove this document's older points (a reprocess), so a
    # search never sees the document with no vectors at all.
    points = [
        ChunkPoint(row["id"], vector, point_payload(row, owner_id, extraction.metadata))
        for row, vector in zip(rows, embedded, strict=True)
    ]
    index_started = time.perf_counter()
    try:
        vectors.ensure_collection(embedder.dimension)
        vectors.upsert(points)
        vectors.delete_document(document_id, keep=[p.id for p in points])
    except Exception as exc:  # noqa: BLE001 - Qdrant unreachable, timed out, ...
        logger.warning("Indexing document %s failed: %s: %s", document_id, type(exc).__name__, exc)
        _fail(session_factory, vectors, document_id, INDEX_UNAVAILABLE)
        return
    timings["index"] = time.perf_counter() - index_started

    store_started = time.perf_counter()
    if not _store(session_factory, document_id, extraction, rows):
        _remove_points(vectors, document_id)  # deleted meanwhile: take our points with it
        return
    timings["store"] = time.perf_counter() - store_started
    logger.info(
        "Document %s ready: %d blocks, %d characters, %s pages -> %d chunks (%s); %s",
        document_id,
        len(extraction.blocks),
        extraction.characters,
        extraction.page_count,
        len(drafts),
        drafts[0].strategy if drafts else "-",
        ", ".join(f"{step} {seconds:.2f} s" for step, seconds in timings.items()),
    )


def _store(
    session_factory: SessionFactory,
    document_id: uuid.UUID,
    extraction: Extraction,
    rows: list[dict],
) -> bool:
    """One transaction: mark ready (only if still processing), replace the chunks, commit.

    Old chunks are deleted first, so reprocessing never leaves two sets. The insert is batched:
    all rows go to the driver in one executemany call, which psycopg 3 pipelines. Measured on
    Neon: 120 rows in 176 ms (~3 round trips), where one round trip per row would be ~7 s.
    """
    with session_factory() as db:
        updated = db.execute(
            update(Document)
            .where(Document.id == document_id, Document.status == "processing")
            .values(
                status="ready",
                page_count=extraction.page_count,
                doc_metadata=extraction.metadata,
                chunk_count=len(rows),
                processed_at=func.now(),
            )
        ).rowcount
        if updated == 0:
            db.rollback()
            logger.info("Document %s was deleted while it was being processed", document_id)
            return False
        db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        if rows:
            db.execute(insert(Chunk), rows)
        db.commit()
    return True


def _remove_points(vectors: VectorStore, document_id: uuid.UUID) -> None:
    """Best effort. If Qdrant is down too, the leftover points belong to a document that is
    failed or gone: searches only return chunks of ready documents found in PostgreSQL, and the
    next reprocess, delete or reindex removes them."""
    try:
        vectors.delete_document(document_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Couldn't remove the points of document %s (%s)", document_id, type(exc).__name__
        )


def _fail(
    session_factory: SessionFactory,
    vectors: VectorStore,
    document_id: uuid.UUID,
    message: str,
) -> None:
    with session_factory() as db:
        updated = db.execute(
            update(Document)
            .where(Document.id == document_id, Document.status == "processing")
            .values(status="failed", error_message=message, chunk_count=0)
        ).rowcount
        if updated:
            # A reprocessed document that now fails must not keep its old chunks...
            db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        db.commit()
    if updated == 0:
        logger.info("Document %s was deleted while it was being processed", document_id)
        return
    _remove_points(vectors, document_id)  # ...or its old vectors


def recover_interrupted(session_factory: SessionFactory, started_at: datetime) -> int:
    """At startup: jobs are in-process (D11), so a restart loses any that were waiting or
    running. Mark them failed with a "please retry" message instead of leaving them spinning.

    Only documents created before this server started are touched, so an upload that arrives
    in the first seconds after startup isn't caught by mistake.
    """
    with session_factory() as db:
        count = db.execute(
            update(Document)
            .where(
                Document.status.in_(("uploaded", "processing")),
                Document.created_at < started_at,
            )
            .values(status="failed", error_message=INTERRUPTED)
        ).rowcount
        db.commit()
    if count:
        logger.warning("Marked %d interrupted document(s) as failed (they can be retried)", count)
    return count
