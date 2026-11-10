"""Response bodies for documents. (Uploads arrive as multipart form data, not JSON.)"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    """What the API reveals about a document. Never `stored_path` (a server detail)."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    kb_id: uuid.UUID
    original_filename: str
    file_type: str
    size_bytes: int
    sha256: str
    status: str  # uploaded | processing | ready | failed | deleting
    error_message: str | None
    page_count: int | None
    chunk_count: int
    # The model attribute is doc_metadata (SQLAlchemy reserves `metadata`); the API says metadata.
    metadata: dict[str, Any] = Field(validation_alias="doc_metadata")
    created_at: datetime
    processed_at: datetime | None


class DocumentList(BaseModel):
    items: list[DocumentOut]
