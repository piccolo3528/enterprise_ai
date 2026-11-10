"""The background ingestion job and the document status lifecycle (ARCHITECTURE §3.1, §4.10).

    uploaded --claim--> processing --> ready
                                   \\-> failed --retry--> uploaded

Rules:
- Each status change is a conditional UPDATE ("... WHERE status = 'processing'"), so a job never
  overwrites a document that was deleted, retried or claimed by someone else meanwhile.
- No database connection is held during extraction: parsing a large PDF can take seconds, and the
  pool has only a handful of connections.
- The job never raises: every outcome ends in `ready` or `failed` with a readable message, and
  unexpected errors are logged with their traceback.

M7 stops after extraction ("ready" = text extracted and checked). M8 adds chunking and M9
embedding to this same job.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.models import Document
from app.services.ingestion.base import ExtractionError
from app.services.ingestion.extractors import extract
from app.services.storage import Storage

logger = logging.getLogger("app.ingestion")

SessionFactory = Callable[[], Session]

UNEXPECTED = (
    "Something went wrong while processing this file. Try again; if it keeps failing, the file "
    "may be damaged."
)
INTERRUPTED = "Processing was interrupted because the server restarted. Please retry."
MISSING_FILE = "The stored file is missing. Delete this document and upload it again."


def process_document(
    session_factory: SessionFactory, storage: Storage, document_id: uuid.UUID
) -> None:
    try:
        _process(session_factory, storage, document_id)
    except Exception:  # noqa: BLE001 - a background job must not crash silently
        logger.exception("Ingestion job for document %s crashed", document_id)


def _process(session_factory: SessionFactory, storage: Storage, document_id: uuid.UUID) -> None:
    with session_factory() as db:
        claimed = db.execute(
            update(Document)
            .where(Document.id == document_id, Document.status == "uploaded")
            .values(status="processing", error_message=None)
            .returning(Document.stored_path, Document.file_type)
        ).one_or_none()
        db.commit()
    if claimed is None:
        logger.info("Document %s is no longer waiting (deleted or claimed); skipping", document_id)
        return

    started = time.perf_counter()
    try:
        extraction = extract(storage.path_of(claimed.stored_path), claimed.file_type)
    except ExtractionError as exc:
        _finish(session_factory, document_id, status="failed", error_message=exc.message)
        logger.info("Document %s failed: %s", document_id, exc.message)
        return
    except FileNotFoundError:
        _finish(session_factory, document_id, status="failed", error_message=MISSING_FILE)
        return
    except Exception:  # noqa: BLE001 - parsers can fail in unforeseen ways on odd files
        logger.exception("Extraction of document %s raised an unexpected error", document_id)
        _finish(session_factory, document_id, status="failed", error_message=UNEXPECTED)
        return

    _finish(
        session_factory,
        document_id,
        status="ready",
        page_count=extraction.page_count,
        doc_metadata=extraction.metadata,
        processed_at=func.now(),
    )
    logger.info(
        "Document %s ready: %d blocks, %d characters, %s pages, %.2f s",
        document_id,
        len(extraction.blocks),
        extraction.characters,
        extraction.page_count,
        time.perf_counter() - started,
    )


def _finish(session_factory: SessionFactory, document_id: uuid.UUID, **values) -> None:
    with session_factory() as db:
        updated = db.execute(
            update(Document)
            .where(Document.id == document_id, Document.status == "processing")
            .values(**values)
        ).rowcount
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
