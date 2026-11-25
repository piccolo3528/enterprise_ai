"""Request and response bodies for conversations (M13)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.answers import CitationOut
from app.schemas.search import clean_user_text

TITLE_MAX = 200  # the column is VARCHAR(200)


class ConversationRename(BaseModel):
    title: str = Field(max_length=TITLE_MAX * 4)  # raw limit; the exact one is below

    @field_validator("title")
    @classmethod
    def _clean_title(cls, value: str) -> str:
        return clean_user_text(value, limit=TITLE_MAX, what="title", empty="Enter a title")


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kb_id: uuid.UUID | None  # None: asks across all your knowledge bases (M16b)
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationList(BaseModel):
    items: list[ConversationOut]


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str  # user | assistant
    content: str  # the question, or the answer (Markdown with [n] citations)
    created_at: datetime
    rewritten_query: str | None  # questions: the standalone version that was searched
    outcome: str | None  # answers: answered | not_found | stopped
    citations: list[CitationOut]  # answers: the cited passages as they were shown
    related: list[CitationOut] = []  # "not found" answers: the closest passages (M16b)
    notices: list[str]
    model: str | None
    latency_ms: dict[str, Any]


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]
