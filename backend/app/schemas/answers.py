"""Request and response bodies for POST /api/knowledge-bases/{kb_id}/ask."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator

from app.schemas.search import clean_user_text

QUESTION_MAX = 1000


class AskRequest(BaseModel):
    question: str = Field(max_length=QUESTION_MAX * 4)  # raw limit; the exact one is below
    # Answer from this document of the knowledge base only (M14); 404 if it isn't in the KB.
    document_id: uuid.UUID | None = None

    @field_validator("question")
    @classmethod
    def _clean_question(cls, value: str) -> str:
        return clean_user_text(value, limit=QUESTION_MAX, what="question", empty="Ask a question")


class CitationOut(BaseModel):
    number: int  # the [n] used in the answer
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    doc_code: str | None
    doc_version: str | None
    doc_status: str | None
    doc_title: str | None
    section: str | None
    page_start: int | None
    page_end: int | None
    text: str  # the whole passage the model was given
    # The passage contains text that looks like instructions to an AI (best-effort heuristic).
    flagged: bool


class AskResponse(BaseModel):
    answer: str  # Markdown with [n] citations; render without raw HTML
    not_found: bool
    citations: list[CitationOut]
    notices: list[str]
    model: str | None  # None when no LLM call was needed
    prompt_tokens: int | None
    output_tokens: int | None
    sources_given: int
    invalid_citations: int
    prompt_version: str
    timings_ms: dict[str, float]
