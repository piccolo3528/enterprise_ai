"""Response of GET /api/stats (M16)."""

from __future__ import annotations

from pydantic import BaseModel


class UserStats(BaseModel):
    knowledge_bases: int
    documents: int  # not counting ones being deleted
    documents_ready: int
    documents_processing: int  # uploaded or processing
    documents_failed: int
    chunks: int  # in ready documents: what search and chat can use
    storage_bytes: int  # the uploaded files' total size
    conversations: int
    questions: int
    questions_7d: int
    not_found_7d: int  # answers in the last 7 days that found nothing in the documents
