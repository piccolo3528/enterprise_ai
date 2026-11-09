from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAt, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.knowledge_base import KnowledgeBase


class User(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "users"
    __table_args__ = (
        # The app lower-cases emails before saving (M5); the database refuses anything else, so
        # "Ana@x.com" and "ana@x.com" can never become two accounts.
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))  # Argon2id (M5), never the password
    full_name: Mapped[str] = mapped_column(String(200))
    settings: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))

    # lazy="raise": touching user.knowledge_bases without loading it explicitly raises an error
    # instead of silently running a query. Each hidden query costs a network round trip.
    knowledge_bases: Mapped[list[KnowledgeBase]] = relationship(
        back_populates="owner", lazy="raise", passive_deletes=True
    )
    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user", lazy="raise", passive_deletes=True
    )
