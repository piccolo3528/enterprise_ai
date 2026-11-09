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


class Conversation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "conversations"
    # The sidebar lists a user's conversations, newest first: one index serves that query.
    __table_args__ = (Index("ix_conversations_user_id_updated_at", "user_id", "updated_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kb_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))

    user: Mapped[User] = relationship(back_populates="conversations", lazy="raise")
    knowledge_base: Mapped[KnowledgeBase] = relationship(
        back_populates="conversations", lazy="raise"
    )
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", lazy="raise", passive_deletes=True
    )


class Message(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(allowed_values("role", MESSAGE_ROLES), name="role"),
        # History is always read in order for one conversation.
        Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    rewritten_query: Mapped[str | None] = mapped_column(Text)  # standalone version (M13)
    citations: Mapped[list[Any]] = mapped_column(server_default=text("'[]'::jsonb"))
    latency_ms: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)

    conversation: Mapped[Conversation] = relationship(back_populates="messages", lazy="raise")
