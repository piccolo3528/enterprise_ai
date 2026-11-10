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

from app.core.errors import ConflictError, NotFoundError
from app.models import Document, KnowledgeBase
from app.services.ingestion.validation import check_content, display_filename, file_type_of
from app.services.knowledge_bases import NOT_FOUND as KB_NOT_FOUND
from app.services.storage import Storage

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


def delete_document(
    db: Session, storage: Storage, owner_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    """Database row first (its chunks cascade), then the file.

    If the file can't be deleted, the leftover is harmless and logged; the reverse order could
    leave a row pointing at a missing file. (M9 adds a first step: Qdrant points by document_id,
    ARCHITECTURE §4.11.) A background job still working on this document finds its row gone
    and stops quietly.
    """
    deleted = db.execute(
        delete(Document)
        .where(*_owned_document(owner_id, document_id))
        .returning(Document.stored_path, Document.kb_id)
        .execution_options(synchronize_session=False)
    ).one_or_none()
    if deleted is None:
        raise NotFoundError(DOCUMENT_NOT_FOUND)
    db.execute(
        update(KnowledgeBase).where(KnowledgeBase.id == deleted.kb_id).values(updated_at=func.now())
    )
    db.commit()
    storage.delete(deleted.stored_path)


def retry_document(db: Session, owner_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    """failed -> uploaded, so the background job can pick it up again."""
    retried = db.scalar(
        update(Document)
        .where(*_owned_document(owner_id, document_id), Document.status == "failed")
        .values(status="uploaded", error_message=None)
        .returning(Document)
        .execution_options(synchronize_session=False)
    )
    if retried is None:
        # Only on this unhappy path: is it missing/not yours (404) or just not failed (409)?
        status = db.scalar(select(Document.status).where(*_owned_document(owner_id, document_id)))
        db.rollback()
        if status is None:
            raise NotFoundError(DOCUMENT_NOT_FOUND)
        raise ConflictError(f"Only failed documents can be retried (this one is {status}).")
    db.commit()
    return retried
