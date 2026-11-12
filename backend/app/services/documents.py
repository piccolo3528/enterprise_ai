"""Documents inside a knowledge base: accept an upload, list, delete, retry. No FastAPI imports.

Same isolation rule as knowledge bases (D36): the caller's id is in every statement, joined
through the knowledge base that owns the document. Someone else's document is "not found".
"""

from __future__ import annotations

import logging
import uuid
from typing import BinaryIO

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ServiceUnavailableError
from app.models import Chunk, Document, KnowledgeBase
from app.services.ingestion.validation import check_content, display_filename, file_type_of
from app.services.knowledge_bases import NOT_FOUND as KB_NOT_FOUND
from app.services.storage import Storage
from app.services.vector_store import VectorStore

logger = logging.getLogger("app.documents")

DOCUMENT_NOT_FOUND = "Document not found."
_DUPLICATE = "uq_documents_kb_id_sha256"


def _owned_document(owner_id: uuid.UUID, document_id: uuid.UUID):
    """WHERE clauses: this document, in a knowledge base the caller owns."""
    return (
        Document.id == document_id,
        Document.kb_id == KnowledgeBase.id,
        KnowledgeBase.owner_id == owner_id,
    )


def require_owned_kb(db: Session, owner_id: uuid.UUID, kb_id: uuid.UUID) -> None:
    """404 unless the caller owns this knowledge base. Checked *before* the upload body is read,
    so nobody can push 20 MB at a knowledge base that isn't theirs."""
    owned = db.scalar(
        select(KnowledgeBase.id).where(
            KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == owner_id
        )
    )
    # End the transaction now: the connection goes back to the pool instead of sitting idle
    # while a slow upload streams in.
    db.rollback()
    if owned is None:
        raise NotFoundError(KB_NOT_FOUND)


def add_document(
    db: Session,
    storage: Storage,
    owner_id: uuid.UUID,
    kb_id: uuid.UUID,
    *,
    filename: str | None,
    source: BinaryIO,
    max_bytes: int,
) -> Document:
    """Validate and store an upload, and record it with status `uploaded`.

    Order matters: file to a temporary name -> content checks -> INSERT (the unique index
    catches duplicates) -> final file name -> COMMIT. Any failure removes the file, so a
    rejected upload leaves nothing behind.
    """
    name = display_filename(filename)
    file_type = file_type_of(name)  # 415 before a single byte is stored
    document_id = uuid.uuid4()
    saved = storage.save_partial(source, kb_id, document_id, file_type, max_bytes)
    try:
        check_content(saved.partial, file_type)
        db.add(
            Document(
                id=document_id,
                kb_id=kb_id,
                original_filename=name,
                stored_path=saved.relative_path,
                file_type=file_type,
                size_bytes=saved.size_bytes,
                sha256=saved.sha256,
            )
        )
        # The KB must still be the caller's (it could have been deleted while the file
        # uploaded); this also marks it as recently changed.
        touched = db.execute(
            update(KnowledgeBase)
            .where(KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == owner_id)
            .values(updated_at=func.now())
        ).rowcount
        if touched == 0:
            raise NotFoundError(KB_NOT_FOUND)
        db.flush()  # INSERT now, so a duplicate is detected before the file is kept
        storage.promote(saved)
        try:
            db.commit()
        except BaseException:
            storage.delete(saved.relative_path)
            raise
    except IntegrityError as exc:
        db.rollback()
        storage.discard(saved)
        if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == _DUPLICATE:
            raise ConflictError("This exact file is already in this knowledge base.") from None
        raise
    except BaseException:
        db.rollback()
        storage.discard(saved)
        raise
    return db.get(Document, document_id)


def list_documents(db: Session, owner_id: uuid.UUID, kb_id: uuid.UUID) -> list[Document]:
    """Newest first. One query: the LEFT JOIN from the knowledge base tells "your KB has no
    documents" (one row, no document) apart from "not your KB" (no rows -> 404)."""
    rows = db.execute(
        select(KnowledgeBase.id, Document)
        .outerjoin(Document, Document.kb_id == KnowledgeBase.id)
        .where(KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == owner_id)
        .order_by(Document.created_at.desc())
    ).all()
    if not rows:
        raise NotFoundError(KB_NOT_FOUND)
    return [document for _, document in rows if document is not None]


INDEX_DELETE_FAILED = (
    "The search index couldn't be updated right now, so nothing was deleted from it yet. "
    "Please try deleting again."
)


def delete_document(
    db: Session,
    storage: Storage,
    vectors: VectorStore,
    owner_id: uuid.UUID,
    document_id: uuid.UUID,
) -> None:
    """The ordered delete of ARCHITECTURE §4.11 (D52):
    mark `deleting` -> Qdrant points -> PostgreSQL row (chunks cascade) -> the file.

    Marking first matters: a background job still indexing this document can only write
    `ready` while the status is `processing`, so once it sees `deleting` it removes the points it
    wrote itself, whatever the timing. If Qdrant is unreachable the document stays `deleting`
    (hidden from search, can't be reprocessed) and deleting it again finishes the job. A file
    that can't be removed at the end is a harmless, logged leftover.
    """
    marked = db.execute(
        update(Document)
        .where(*_owned_document(owner_id, document_id))
        .values(status="deleting")
        .returning(Document.stored_path, Document.kb_id)
        .execution_options(synchronize_session=False)
    ).one_or_none()
    if marked is None:
        db.rollback()
        raise NotFoundError(DOCUMENT_NOT_FOUND)
    db.commit()
    try:
        vectors.delete_document(document_id)
    except Exception as exc:  # noqa: BLE001 - Qdrant down or timed out
        logger.warning("Deleting points of document %s failed: %s", document_id, exc)
        raise ServiceUnavailableError(INDEX_DELETE_FAILED) from None
    db.execute(delete(Document).where(Document.id == document_id))
    db.execute(
        update(KnowledgeBase).where(KnowledgeBase.id == marked.kb_id).values(updated_at=func.now())
    )
    db.commit()
    storage.delete(marked.stored_path)


REPROCESSABLE = ("failed", "ready")


def reprocess_document(db: Session, owner_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    """failed or ready -> uploaded, so the background job runs again: after a failure, or to
    rebuild chunks when the chunking settings change (and for documents from before M8)."""
    queued = db.scalar(
        update(Document)
        .where(*_owned_document(owner_id, document_id), Document.status.in_(REPROCESSABLE))
        .values(status="uploaded", error_message=None)
        .returning(Document)
        .execution_options(synchronize_session=False)
    )
    if queued is None:
        # Only on this unhappy path: is it missing/not yours (404) or busy (409)?
        status = db.scalar(select(Document.status).where(*_owned_document(owner_id, document_id)))
        db.rollback()
        if status is None:
            raise NotFoundError(DOCUMENT_NOT_FOUND)
        raise ConflictError(f"This document is already being processed ({status}).")
    db.commit()
    return queued


def get_document(db: Session, owner_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    document = db.scalar(select(Document).where(*_owned_document(owner_id, document_id)))
    if document is None:
        raise NotFoundError(DOCUMENT_NOT_FOUND)
    return document


def list_chunks(
    db: Session, owner_id: uuid.UUID, document_id: uuid.UUID, *, offset: int, limit: int
) -> tuple[list[Chunk], int]:
    """A page of the document's chunks in order, plus the total. Two reads: the page (ownership
    joined in) and the document, which supplies the total (`chunk_count`) and decides 404,
    since an empty page alone can't tell "no chunks" from "not yours"."""
    chunks = list(
        db.scalars(
            select(Chunk)
            .join(Document, Chunk.document_id == Document.id)
            .join(KnowledgeBase, Document.kb_id == KnowledgeBase.id)
            .where(Chunk.document_id == document_id, KnowledgeBase.owner_id == owner_id)
            .order_by(Chunk.chunk_index)
            .offset(offset)
            .limit(limit)
        )
    )
    document = get_document(db, owner_id, document_id)  # 404 if missing / not yours
    return chunks, document.chunk_count
