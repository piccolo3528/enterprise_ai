from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.document import Document
    from app.models.user import User


class KnowledgeBase(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "knowledge_bases"
    # Names are unique per owner. The constraint's index starts with owner_id, so it also serves
    # "list this user's knowledge bases"; a separate owner_id index would be redundant.
    __table_args__ = (UniqueConstraint("owner_id", "name"),)

    # ON DELETE CASCADE: deleting a user deletes their knowledge bases in the database itself,
    # in one statement, without the app loading every child row first.
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)

    owner: Mapped[User] = relationship(back_populates="knowledge_bases", lazy="raise")
    documents: Mapped[list[Document]] = relationship(
        back_populates="knowledge_base", lazy="raise", passive_deletes=True
    )
    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="knowledge_base", lazy="raise", passive_deletes=True
    )
