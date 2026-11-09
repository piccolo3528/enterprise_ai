from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Computed, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.document import Document


class Chunk(UUIDPrimaryKey, Base):
    """A piece of a document. Its id is also its Qdrant point id; the text lives only here."""

    __tablename__ = "chunks"
    __table_args__ = (
        # Also the index for "this document's chunks, in order" (leading column document_id).
        UniqueConstraint("document_id", "chunk_index"),
        # GIN index for keyword search, the setup verified on Neon in M1.
        Index("ix_chunks_search_vector", "search_vector", postgresql_using="gin"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    # Copied from the document so searches can filter by knowledge base without a join.
    kb_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(300))  # e.g. "§4.2 Annual leave" (S3)
    token_count: Mapped[int] = mapped_column(Integer)
    strategy: Mapped[str] = mapped_column(String(30))  # which chunker produced it (M8)
    # Computed by PostgreSQL from `text` on every insert/update, so it can never be stale.
    # deferred: not loaded with the row unless asked for; the app only ever searches it.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', text)", persisted=True), deferred=True
    )

    document: Mapped[Document] = relationship(back_populates="chunks", lazy="raise")
