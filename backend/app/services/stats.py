"""Dashboard numbers for one user (M16): one query, one round trip.

Each number is a scalar subquery of a single SELECT, so the dashboard costs one round trip
(~55 ms to Neon Singapore) however many numbers it shows (L24's budget: <= 2 queries a request).
Everything is filtered by owner, like every other read (§4.8).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Conversation, Document, KnowledgeBase, Message

RECENT = timedelta(days=7)


def user_stats(db: Session, user_id: uuid.UUID) -> dict[str, int]:
    owned_kbs = select(KnowledgeBase.id).where(KnowledgeBase.owner_id == user_id)
    docs = Document.kb_id.in_(owned_kbs.scalar_subquery()) & (Document.status != "deleting")

    def count_docs(*conditions):
        return select(func.count()).where(docs, *conditions).scalar_subquery()

    user_conversations = select(Conversation.id).where(Conversation.user_id == user_id)
    questions = Message.conversation_id.in_(user_conversations.scalar_subquery()) & (
        Message.role == "user"
    )
    answers = Message.conversation_id.in_(user_conversations.scalar_subquery()) & (
        Message.role == "assistant"
    )
    since = func.now() - RECENT

    row = db.execute(
        select(
            select(func.count()).select_from(owned_kbs.subquery()).scalar_subquery()
            .label("knowledge_bases"),
            count_docs().label("documents"),
            count_docs(Document.status == "ready").label("documents_ready"),
            count_docs(Document.status.in_(("uploaded", "processing")))
            .label("documents_processing"),
            count_docs(Document.status == "failed").label("documents_failed"),
            select(func.coalesce(func.sum(Document.chunk_count), 0))
            .where(docs, Document.status == "ready").scalar_subquery().label("chunks"),
            select(func.coalesce(func.sum(Document.size_bytes), 0))
            .where(docs).scalar_subquery().label("storage_bytes"),
            select(func.count()).select_from(user_conversations.subquery()).scalar_subquery()
            .label("conversations"),
            select(func.count()).where(questions).scalar_subquery().label("questions"),
            select(func.count()).where(questions, Message.created_at >= since)
            .scalar_subquery().label("questions_7d"),
            select(func.count()).where(answers, Message.created_at >= since,
                                       Message.outcome == "not_found")
            .scalar_subquery().label("not_found_7d"),
        )  # fmt: skip
    ).one()
    return {key: int(value) for key, value in row._mapping.items()}
