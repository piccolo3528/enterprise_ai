"""Request and response bodies for POST /api/knowledge-bases/{kb_id}/search."""

from __future__ import annotations

import re
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

QUERY_MAX = 500
TOP_K_MAX = 50

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # tabs are fine; line breaks are collapsed
_WHITESPACE_RUN = re.compile(r"\s+")


class SearchRequest(BaseModel):
    query: str = Field(max_length=QUERY_MAX * 4)  # raw limit; the exact one is checked below
    mode: Literal["semantic", "keyword", "hybrid"] = "hybrid"
    top_k: int = Field(default=10, ge=1, le=TOP_K_MAX)
    # Restrict the search to one document of this knowledge base.
    document_id: uuid.UUID | None = None
    # Minimum cosine similarity for semantic hits (semantic and hybrid modes); None = no limit.
    min_score: float | None = Field(default=None, ge=0, le=1)

    @field_validator("query")
    @classmethod
    def _clean_query(cls, value: str) -> str:
        # NUL would make PostgreSQL fail (a 500); other control characters are never typed.
        if _CONTROL.search(value):
            raise ValueError("The search contains characters that aren't allowed")
        value = _WHITESPACE_RUN.sub(" ", value).strip()
        if not value:
            raise ValueError("Enter something to search for")
        if len(value) > QUERY_MAX:
            raise ValueError(f"Use at most {QUERY_MAX} characters")
        return value


class SearchResultOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    # Front matter of the document, when it has one (S2): e.g. NX-HR-002, 3.0, current.
    doc_code: str | None
    doc_version: str | None
    doc_status: str | None
    chunk_index: int
    section: str | None
    page_start: int | None
    page_end: int | None
    text: str
    # The mode's score: cosine similarity (semantic), matched words + rank (keyword), or the
    # RRF score (hybrid). Each retriever's own rank and score are shown alongside.
    score: float
    semantic_rank: int | None
    semantic_score: float | None
    keyword_rank: int | None
    keyword_score: float | None
    keyword_matched: int | None


class SearchResponse(BaseModel):
    mode: str
    results: list[SearchResultOut]
    query_terms: int | None
    notice: str | None
    timings_ms: dict[str, float]
