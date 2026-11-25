from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAt, Timestamps, UUIDPrimaryKey, allowed_values

if TYPE_CHECKING:
    from app.models.knowledge_base import KnowledgeBase
    from app.models.user import User

MESSAGE_ROLES = ("user", "assistant")
# Assistant messages only (NULL for questions): an answer, the "not found" reply, or the part of
# an answer the user saw before pressing Stop.
MESSAGE_OUTCOMES = ("answered", "not_found", "stopped")


class Conversation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "conversations"
    # The sidebar lists a user's conversations, newest first: one index serves that query.
    __table_args__ = (Index("ix_conversations_user_id_updated_at", "user_id", "updated_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # NULL (M16b): the conversation asks across all of its owner's knowledge bases.
    kb_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))

    user: Mapped[User] = relationship(back_populates="conversations", lazy="raise")
    knowledge_base: Mapped[KnowledgeBase | None] = relationship(
        back_populates="conversations", lazy="raise"
    )
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", lazy="raise", passive_deletes=True
    )


class Message(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(allowed_values("role", MESSAGE_ROLES), name="role"),
        CheckConstraint(allowed_values("outcome", MESSAGE_OUTCOMES), name="outcome"),
        # History is always read in order for one conversation: by created_at (set to
        # clock_timestamp() when saved), question first on a tie (services/conversations.py).
        Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    # On a follow-up question: the standalone version that was searched (M13).
    rewritten_query: Mapped[str | None] = mapped_column(Text)
    # A snapshot of each cited passage as shown (document, version, section, text): the
    # conversation stays readable after the document is reprocessed or deleted.
    citations: Mapped[list[Any]] = mapped_column(server_default=text("'[]'::jsonb"))
    # A "not found" answer: the closest passages it was given, not cited (M16b), as snapshots.
    related: Mapped[list[Any]] = mapped_column(server_default=text("'[]'::jsonb"))
    notices: Mapped[list[Any]] = mapped_column(server_default=text("'[]'::jsonb"))
    outcome: Mapped[str | None] = mapped_column(String(20))
    prompt_version: Mapped[str | None] = mapped_column(String(30))
    latency_ms: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)

    conversation: Mapped[Conversation] = relationship(back_populates="messages", lazy="raise")
