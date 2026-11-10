"""Knowledge bases: create, list, read, rename and delete. No FastAPI imports.

Tenant isolation rule: **every statement carries `owner_id = :caller`**. Ownership is never
checked in a separate query first ("is it yours?" then "change it"):
- one statement is one round trip instead of two (the L24 budget), and
- nothing can change between the check and the action (no time-of-check/time-of-use gap).

A knowledge base that doesn't exist and one that belongs to someone else are indistinguishable:
both are "not found" (404), so the API never confirms that someone else's id is real.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, Select, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import Conversation, Document, KnowledgeBase

NOT_FOUND = "Knowledge base not found."
_NAME_INDEX = "uq_knowledge_bases_owner_id_lower_name"


@dataclass(frozen=True)
class KnowledgeBaseSummary:
    """A knowledge base plus the counts the UI shows next to it."""

    kb: KnowledgeBase
    document_count: int
    conversation_count: int

    def as_dict(self) -> dict:
        kb = self.kb
        return {
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "document_count": self.document_count,
            "conversation_count": self.conversation_count,
            "created_at": kb.created_at,
            "updated_at": kb.updated_at,
        }


def _counts() -> tuple[ColumnElement[int], ColumnElement[int]]:
    """Correlated subqueries: the counts come back in the same statement as the rows.

    Each is an index-only lookup: documents' (kb_id, sha256) unique index and conversations'
    kb_id index both start with kb_id.
    """
    documents = (
        select(func.count())
        .select_from(Document)
        .where(Document.kb_id == KnowledgeBase.id)
        .correlate(KnowledgeBase)
        .scalar_subquery()
    )
    conversations = (
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.kb_id == KnowledgeBase.id)
        .correlate(KnowledgeBase)
        .scalar_subquery()
    )
    return documents.label("document_count"), conversations.label("conversation_count")


def _owned(owner_id: uuid.UUID) -> Select:
    return select(KnowledgeBase, *_counts()).where(KnowledgeBase.owner_id == owner_id)


def _duplicate_name(name: str) -> ConflictError:
    return ConflictError(f'You already have a knowledge base called "{name}".')


def _is_duplicate_name(exc: IntegrityError) -> bool:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == _NAME_INDEX


def list_knowledge_bases(db: Session, owner_id: uuid.UUID) -> list[KnowledgeBaseSummary]:
    """The caller's knowledge bases, most recently changed first. One query."""
    rows = db.execute(
        _owned(owner_id).order_by(KnowledgeBase.updated_at.desc(), KnowledgeBase.name)
    )
    return [KnowledgeBaseSummary(*row) for row in rows]


def get_knowledge_base(db: Session, owner_id: uuid.UUID, kb_id: uuid.UUID) -> KnowledgeBaseSummary:
    row = db.execute(_owned(owner_id).where(KnowledgeBase.id == kb_id)).one_or_none()
    if row is None:
        raise NotFoundError(NOT_FOUND)
    return KnowledgeBaseSummary(*row)


def create_knowledge_base(
    db: Session, owner_id: uuid.UUID, *, name: str, description: str | None
) -> KnowledgeBaseSummary:
    kb = KnowledgeBase(owner_id=owner_id, name=name, description=description)
    db.add(kb)
    try:
        # No "is the name taken?" query first: the unique index answers in the same round trip,
        # and two simultaneous creates can't both win.
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _is_duplicate_name(exc):
            raise _duplicate_name(name) from None
        raise
    return KnowledgeBaseSummary(kb, document_count=0, conversation_count=0)


def update_knowledge_base(
    db: Session, owner_id: uuid.UUID, kb_id: uuid.UUID, changes: dict[str, str | None]
) -> KnowledgeBaseSummary:
    """Rename and/or change the description. One UPDATE … RETURNING, scoped to the owner."""
    statement = (
        update(KnowledgeBase)
        .where(KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == owner_id)
        .values(**changes)  # updated_at is set by the column's onupdate=now()
        .returning(KnowledgeBase, *_counts())
        .execution_options(synchronize_session=False)
    )
    try:
        row = db.execute(statement).one_or_none()
    except IntegrityError as exc:
        db.rollback()
        if _is_duplicate_name(exc):
            raise _duplicate_name(changes["name"]) from None
        raise
    if row is None:
        # Nothing matched, so nothing changed: the session is closed (and rolled back) by the
        # request's dependency.
        raise NotFoundError(NOT_FOUND)
    db.commit()
    return KnowledgeBaseSummary(*row)


def delete_knowledge_base(db: Session, owner_id: uuid.UUID, kb_id: uuid.UUID) -> None:
    """Delete a knowledge base and, through ON DELETE CASCADE, its documents, chunks,
    conversations and messages: one statement, scoped to the owner.

    The route then removes the upload folder (M7). M9 adds the first step of the ordered delete
    in ARCHITECTURE §4.11: Qdrant points by kb_id -> PostgreSQL rows -> the upload folder, so a
    failure part-way leaves only harmless leftovers.
    """
    deleted = db.execute(
        delete(KnowledgeBase)
        .where(KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == owner_id)
        .returning(KnowledgeBase.id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    if deleted is None:
        raise NotFoundError(NOT_FOUND)
    db.commit()
