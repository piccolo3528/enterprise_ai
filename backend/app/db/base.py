"""Declarative base and column mixins shared by every model (ARCHITECTURE section 5)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Every constraint and index gets a predictable name (e.g. "fk_documents_kb_id_knowledge_bases").
# Without this, PostgreSQL invents names, and a later migration can't reliably drop or alter them.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def allowed_values(column: str, values: tuple[str, ...]) -> str:
    """SQL for a CHECK constraint, e.g. "status IN ('ready', 'failed')".

    Used instead of PostgreSQL ENUM types: adding a value later is a one-line migration rather
    than an ALTER TYPE dance.
    """
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB}


class UUIDPrimaryKey:
    """UUID ids generated in Python, not by the database.

    The app knows a row's id before inserting it, so no extra round trip is needed to read it
    back, and a chunk's id can be used straight away as its Qdrant point id. UUIDs also can't be
    guessed or enumerated the way 1, 2, 3 can.
    """

    # sort_order: mixin columns would otherwise come last; id first reads better in the console.
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, sort_order=-10
    )


class CreatedAt:
    # Set by PostgreSQL (one clock for everyone) and returned in the same INSERT via RETURNING.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), sort_order=100
    )


class Timestamps(CreatedAt):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), sort_order=101
    )
