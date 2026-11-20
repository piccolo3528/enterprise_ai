"""Conversations and their messages: list, read, rename, delete, and saving a finished turn (M13).

Same tenant rule as knowledge bases: every statement carries `user_id = :caller`, and someone
else's conversation is "not found" (404), exactly like one that doesn't exist.

**A conversation is created by its first answered question** (D70). The stream generates the id
up front and saves the conversation, the question and the answer in one transaction at the end.
A first question that fails leaves nothing behind (no empty "New conversation" rows), and a
question is never saved without its answer.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Conversation, KnowledgeBase, Message

logger = logging.getLogger("app.conversations")

NOT_FOUND = "Conversation not found."
KB_NOT_FOUND = "Knowledge base not found."
TITLE_MAX = 80  # characters of the first question used as the title
LIST_LIMIT = 100

# Messages are stamped with clock_timestamp() (the time of each INSERT, unlike now(), which is
# the transaction's start). A question and its answer are inserted together and may still share
# the microsecond, so the question comes first on a tie.
_IN_ORDER = (Message.created_at, case((Message.role == "user", 0), else_=1))


def title_from(question: str) -> str:
    """The first question, cut at a word boundary to TITLE_MAX characters."""
    if len(question) <= TITLE_MAX:
        return question
    cut = question[: TITLE_MAX - 1]
    if " " in cut[TITLE_MAX // 2 :]:
        cut = cut[: cut.rindex(" ")]
    return cut.rstrip(" ,;:-") + "…"


def check_knowledge_base(db: Session, owner_id: uuid.UUID, kb_id: uuid.UUID) -> None:
    """404 unless the caller owns the knowledge base. One index lookup."""
    found = db.scalar(
        select(KnowledgeBase.id).where(
            KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == owner_id
        )
    )
    if found is None:
        raise NotFoundError(KB_NOT_FOUND)


def list_conversations(db: Session, owner_id: uuid.UUID, kb_id: uuid.UUID) -> list[Conversation]:
    """The caller's conversations about one knowledge base, most recent first. One query: the
    outer join returns the knowledge base's row even when it has no conversations, so a KB that
    isn't yours is a 404, not an empty list."""
    rows = db.execute(
        select(KnowledgeBase.id, Conversation)
        .outerjoin(
            Conversation,
            (Conversation.kb_id == KnowledgeBase.id) & (Conversation.user_id == owner_id),
        )
        .where(KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == owner_id)
        .order_by(Conversation.updated_at.desc())
        .limit(LIST_LIMIT)
    ).all()
    if not rows:
        raise NotFoundError(KB_NOT_FOUND)
    return [conversation for _, conversation in rows if conversation is not None]


def get_conversation(
    db: Session, owner_id: uuid.UUID, conversation_id: uuid.UUID
) -> tuple[Conversation, list[Message]]:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == owner_id
        )
    )
    if conversation is None:
        raise NotFoundError(NOT_FOUND)
    messages = db.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(*_IN_ORDER)
    ).all()
    return conversation, list(messages)


def load_for_follow_up(
    db: Session, owner_id: uuid.UUID, conversation_id: uuid.UUID, *, max_turns: int
) -> tuple[uuid.UUID, list[tuple[str, str]]]:
    """(knowledge base id, the last `max_turns` question/answer pairs as (role, text), oldest
    first). 404 if the conversation isn't the caller's."""
    kb_id = db.scalar(
        select(Conversation.kb_id).where(
            Conversation.id == conversation_id, Conversation.user_id == owner_id
        )
    )
    if kb_id is None:
        raise NotFoundError(NOT_FOUND)
    newest_first = db.execute(
        select(Message.role, Message.content)
        .where(Message.conversation_id == conversation_id)
        .order_by(*(column.desc() for column in _IN_ORDER))
        .limit(2 * max_turns)
    ).all()
    return kb_id, [(role, content) for role, content in reversed(newest_first)]


def rename_conversation(
    db: Session, owner_id: uuid.UUID, conversation_id: uuid.UUID, title: str
) -> Conversation:
    conversation = db.scalar(
        update(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == owner_id)
        # Keep updated_at (its onupdate would bump it): the list is ordered by activity, and
        # renaming isn't activity.
        .values(title=title, updated_at=Conversation.updated_at)
        .returning(Conversation)
    )
    if conversation is None:
        raise NotFoundError(NOT_FOUND)
    db.commit()
    return conversation


def delete_conversation(db: Session, owner_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
    """Its messages go with it (ON DELETE CASCADE)."""
    deleted = db.execute(
        delete(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == owner_id
        )
    ).rowcount
    if not deleted:
        raise NotFoundError(NOT_FOUND)
    db.commit()


@dataclass
class AnswerRecord:
    """What is saved about an answer (the assistant message)."""

    content: str
    outcome: str  # answered | not_found | stopped
    citations: list[dict[str, Any]] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    model: str | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    prompt_version: str | None = None
    latency_ms: dict[str, float] = field(default_factory=dict)


def save_turn(
    db: Session,
    *,
    owner_id: uuid.UUID,
    kb_id: uuid.UUID,
    conversation_id: uuid.UUID,
    new: bool,
    question: str,
    rewritten_query: str | None,
    answer: AnswerRecord,
) -> uuid.UUID:
    """Save a question and its answer in one transaction (creating the conversation for a first
    question). Returns the answer's message id. 404 if the conversation (or, for a new one, the
    knowledge base) was deleted while the answer was being written."""
    if new:
        db.add(Conversation(id=conversation_id, user_id=owner_id, kb_id=kb_id,
                            title=title_from(question)))  # fmt: skip
    else:
        touched = db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id, Conversation.user_id == owner_id)
            .values(updated_at=func.now())
        ).rowcount
        if not touched:
            raise NotFoundError(NOT_FOUND)
    reply = Message(
        conversation_id=conversation_id,
        created_at=func.clock_timestamp(),
        role="assistant",
        content=answer.content,
        outcome=answer.outcome,
        citations=answer.citations,
        notices=answer.notices,
        model=answer.model,
        prompt_tokens=answer.prompt_tokens,
        output_tokens=answer.output_tokens,
        prompt_version=answer.prompt_version,
        latency_ms=answer.latency_ms,
    )
    db.add_all(
        [
            Message(
                conversation_id=conversation_id,
                created_at=func.clock_timestamp(),
                role="user",
                content=question,
                rewritten_query=rewritten_query,
            ),
            reply,
        ]
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # A new conversation's knowledge base was deleted meanwhile (FK violation).
        raise NotFoundError(KB_NOT_FOUND if new else NOT_FOUND) from None
    return reply.id
