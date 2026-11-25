"""Response model for GET /api/health (also documents the shape in /docs)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ServiceCheck(BaseModel):
    status: Literal["ok", "error"]
    latency_ms: float | None = None  # how long the check took, as seen from this machine
    detail: str | None = None  # short and safe to show; the full error is in the server log


class DatabaseCheck(ServiceCheck):
    size_bytes: int | None = None  # pg_database_size of this database (M16)


class VectorStoreCheck(ServiceCheck):
    collection: str
    collection_exists: bool | None = None  # False until the first documents are indexed (M9)


class LlmInfo(BaseModel):
    provider: Literal["gemini"] = "gemini"
    api_key_configured: bool  # checked locally; the health check spends no Gemini quota
    answer_model: str
    utility_model: str
    fallback_configured: bool  # a backup model is configured (Gemini backup or Groq, D80)


class Services(BaseModel):
    database: DatabaseCheck
    vector_store: VectorStoreCheck
    llm: LlmInfo


class RetrievalInfo(BaseModel):
    """The server's answer pipeline settings (backend/.env), shown read-only in Settings (M16)."""

    chunk_strategy: str
    chunk_size_tokens: int
    retrieval_top_k: int
    context_max_sources: int
    multi_query_enabled: bool
    rerank_enabled: bool
    version_mode: str
    temperature: float


class ModelsInfo(BaseModel):
    embedding: str
    reranker: str


class PublicHealth(BaseModel):
    """Without a session (M16): only "the API process is up". No checks run, so the public
    endpoint can't be used to make the server call Neon/Qdrant, and it reveals no versions or
    model names."""

    status: Literal["ok"] = "ok"


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    services: Services
    models: ModelsInfo
    retrieval: RetrievalInfo
