"""Response model for GET /api/health (also documents the shape in /docs)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ServiceCheck(BaseModel):
    status: Literal["ok", "error"]
    latency_ms: float | None = None  # how long the check took, as seen from this machine
    detail: str | None = None  # short and safe to show; the full error is in the server log


class VectorStoreCheck(ServiceCheck):
    collection: str
    collection_exists: bool | None = None  # False until the first documents are indexed (M9)


class LlmInfo(BaseModel):
    provider: Literal["gemini"] = "gemini"
    api_key_configured: bool  # checked locally; the health check spends no Gemini quota
    answer_model: str
    utility_model: str
    fallback_configured: bool  # Groq key present (D22, not wired in yet)


class Services(BaseModel):
    database: ServiceCheck
    vector_store: VectorStoreCheck
    llm: LlmInfo


class ModelsInfo(BaseModel):
    embedding: str
    reranker: str


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    services: Services
    models: ModelsInfo
