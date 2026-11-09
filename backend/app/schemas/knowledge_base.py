"""Request and response bodies for /api/knowledge-bases."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NAME_MAX = 120  # the column is VARCHAR(120)
DESCRIPTION_MAX = 1000

# Control characters have no place in a name. NUL (\x00) matters most: PostgreSQL refuses it in
# text columns, so without this check it would reach the database and come back as a 500.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RUN = re.compile(r"\s+")


def clean_name(value: str) -> str:
    """Trim, collapse inner whitespace ("HR   policies" → "HR policies"), reject the rest."""
    if _CONTROL.search(value):
        raise ValueError("Name contains characters that aren't allowed")
    value = _WHITESPACE_RUN.sub(" ", value).strip()
    if not value:
        raise ValueError("Enter a name")
    if len(value) > NAME_MAX:
        raise ValueError(f"Use at most {NAME_MAX} characters")
    return value


def clean_description(value: str | None) -> str | None:
    """Trim; an empty description is stored as no description. Line breaks and tabs are kept."""
    if value is None:
        return None
    if _CONTROL.search(value):
        raise ValueError("Description contains characters that aren't allowed")
    value = value.strip()
    if len(value) > DESCRIPTION_MAX:
        raise ValueError(f"Use at most {DESCRIPTION_MAX} characters")
    return value or None


class KnowledgeBaseCreate(BaseModel):
    # Generous raw limits stop megabyte payloads early; the exact rules are in the validators,
    # which run after whitespace is collapsed.
    name: str = Field(max_length=NAME_MAX * 4)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX * 4)

    _name = field_validator("name")(clean_name)
    _description = field_validator("description")(clean_description)


class KnowledgeBaseUpdate(BaseModel):
    """PATCH: only the fields sent are changed. `"description": null` clears the description."""

    name: str | None = Field(default=None, max_length=NAME_MAX * 4)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX * 4)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str:
        if v is None:
            raise ValueError("A knowledge base must have a name")
        return clean_name(v)

    _description = field_validator("description")(clean_description)

    @model_validator(mode="after")
    def _something_to_change(self) -> KnowledgeBaseUpdate:
        if not self.model_fields_set:
            raise ValueError("Send a name or a description to change")
        return self

    def changes(self) -> dict[str, str | None]:
        """Only the fields the client actually sent (an omitted field is left alone)."""
        return self.model_dump(include=self.model_fields_set)


class KnowledgeBaseOut(BaseModel):
    """What the API returns. The owner id is left out: it's always the caller."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    document_count: int
    conversation_count: int
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseList(BaseModel):
    # An object rather than a bare list, so paging fields can be added later without breaking
    # clients.
    items: list[KnowledgeBaseOut]
