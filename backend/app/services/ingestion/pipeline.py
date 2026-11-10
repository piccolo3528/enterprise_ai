"""The background ingestion job and the document status lifecycle (ARCHITECTURE §3.1, §4.10).

    uploaded --claim--> processing --> ready  --reprocess--> uploaded
                                   \\-> failed --reprocess--> uploaded

Rules:
- Each status change is a conditional UPDATE ("... WHERE status = 'processing'"), so a job never
  overwrites a document that was deleted, retried or claimed by someone else meanwhile.
- No database connection is held during extraction: parsing a large PDF can take seconds, and the
  pool has only a handful of connections.
- The job never raises: every outcome ends in `ready` or `failed` with a readable message, and
  unexpected errors are logged with their traceback.

Since M8 the job extracts AND chunks; "ready" means the chunks are stored. M9 adds embedding to
this same job.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, insert, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Chunk, Document
from app.services.ingestion.base import Extraction, ExtractionError
from app.services.ingestion.chunking import ChunkDraft, chunk_document
from app.services.ingestion.extractors import extract
from app.services.ingestion.tokens import get_tokens
from app.services.storage import Storage

logger = logging.getLogger("app.ingestion")

SessionFactory = Callable[[], Session]

UNEXPECTED = (
    "Something went wrong while processing this file. Try again; if it keeps failing, the file "
    "may be damaged."
)
INTERRUPTED = "Processing was interrupted because the server restarted. Please retry."
MISSING_FILE = "The stored file is missing. Delete this document and upload it again."


@dataclass(frozen=True)
class ChunkingConfig:
    """What the job needs from Settings (kept small so scripts and tests can build one)."""

    embedding_model: str
    strategy: str = "auto"
    size: int = 400
    overlap: int = 60

    @classmethod
    def from_settings(cls, settings: Settings) -> ChunkingConfig:
        return cls(
            embedding_model=settings.embedding_model,
            strategy=settings.chunk_strategy,
            size=settings.chunk_size_tokens,
            overlap=settings.chunk_overlap_tokens,
        )


def process_document(
    session_factory: SessionFactory,
    storage: Storage,
    config: ChunkingConfig,
    document_id: uuid.UUID,
) -> None:
    try:
        _process(session_factory, storage, config, document_id)
    except Exception:  # noqa: BLE001 - a background job must not crash silently
        logger.exception("Ingestion job for document %s crashed", document_id)


def _process(
    session_factory: SessionFactory,
    storage: Storage,
    config: ChunkingConfig,
    document_id: uuid.UUID,
) -> None:
    with session_factory() as db:
        claimed = db.execute(
            update(Document)
            .where(Document.id == document_id, Document.status == "uploaded")
            .values(status="processing", error_message=None)
            .returning(Document.stored_path, Document.file_type, Document.kb_id)
        ).one_or_none()
        db.commit()
    if claimed is None:
        logger.info("Document %s is no longer waiting (deleted or claimed); skipping", document_id)
        return

    # CPU work, with no database connection held.
    started = time.perf_counter()
    try:
        extraction = extract(storage.path_of(claimed.stored_path), claimed.file_type)
        drafts = chunk_document(
            extraction.blocks,
            extraction.metadata,
            get_tokens(config.embedding_model),
            strategy=config.strategy,
            size=config.size,
            overlap=config.overlap,
        )
    except ExtractionError as exc:
        _fail(session_factory, document_id, exc.message)
        logger.info("Document %s failed: %s", document_id, exc.message)
        return
    except FileNotFoundError:
        _fail(session_factory, document_id, MISSING_FILE)
        return
    except Exception:  # noqa: BLE001 - parsers can fail in unforeseen ways on odd files
        logger.exception("Processing of document %s raised an unexpected error", document_id)
        _fail(session_factory, document_id, UNEXPECTED)
        return
    parsed = time.perf_counter() - started

    stored = _store(session_factory, document_id, claimed.kb_id, extraction, drafts)
    if stored:
        logger.info(
            "Document %s ready: %d blocks, %d characters, %s pages -> %d chunks (%s); "
            "parse+chunk %.2f s, store %.2f s",
            document_id,
            len(extraction.blocks),
            extraction.characters,
            extraction.page_count,
            len(drafts),
            drafts[0].strategy if drafts else "-",
            parsed,
            time.perf_counter() - started - parsed,
        )


def _store(
    session_factory: SessionFactory,
    document_id: uuid.UUID,
    kb_id: uuid.UUID,
    extraction: Extraction,
    drafts: list[ChunkDraft],
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
                chunk_count=len(drafts),
                processed_at=func.now(),
            )
        ).rowcount
        if updated == 0:
            db.rollback()
            logger.info("Document %s was deleted while it was being processed", document_id)
            return False
        db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        if drafts:
            db.execute(
                insert(Chunk),
                [
                    {
                        # Generated here: the chunk id is also its Qdrant point id (M9).
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
                ],
            )
        db.commit()
    return True


def _fail(session_factory: SessionFactory, document_id: uuid.UUID, message: str) -> None:
    with session_factory() as db:
        updated = db.execute(
            update(Document)
            .where(Document.id == document_id, Document.status == "processing")
            .values(status="failed", error_message=message, chunk_count=0)
        ).rowcount
        if updated:
            # A reprocessed document that now fails must not keep its old chunks.
            db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        db.commit()
    if updated == 0:
        logger.info("Document %s was deleted while it was being processed", document_id)


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
