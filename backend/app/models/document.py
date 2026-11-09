from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAt, UUIDPrimaryKey, allowed_values

if TYPE_CHECKING:
    from app.models.chunk import Chunk
    from app.models.knowledge_base import KnowledgeBase

FILE_TYPES = ("pdf", "docx", "txt", "md")
DOCUMENT_STATUSES = ("uploaded", "processing", "ready", "failed", "deleting")


class Document(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(allowed_values("file_type", FILE_TYPES), name="file_type"),
        CheckConstraint(allowed_values("status", DOCUMENT_STATUSES), name="status"),
        # The same file (by content hash) can't be uploaded twice into one knowledge base. Its
        # index starts with kb_id, so it also serves "list this KB's documents".
        UniqueConstraint("kb_id", "sha256"),
    )

    kb_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"))
    original_filename: Mapped[str] = mapped_column(String(255))  # data only, never a file path
    stored_path: Mapped[str] = mapped_column(String(500))  # server-generated name (M7)
    file_type: Mapped[str] = mapped_column(String(10))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), server_default="uploaded")
    error_message: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # Markdown front matter (S2): document_id, version, status, effective_date, amends, ...
    # The attribute can't be called `metadata`: SQLAlchemy reserves that name on every model.
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", server_default=text("'{}'::jsonb")
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    knowledge_base: Mapped[KnowledgeBase] = relationship(back_populates="documents", lazy="raise")
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", lazy="raise", passive_deletes=True
    )
