"""The LLM layer: provider interface, Gemini client, rate limiter, prompt templates (§4.7)."""

from __future__ import annotations

from app.core.config import Settings
from app.services.llm.base import LLMProvider, LLMResult
from app.services.llm.gemini import GeminiClient
from app.services.llm.rate_limiter import TokenBucket

__all__ = ["GeminiClient", "LLMProvider", "LLMResult", "TokenBucket", "build_llm"]


def build_llm(settings: Settings) -> LLMProvider | None:
    """The answer model, or None when GEMINI_API_KEY isn't set (search keeps working; asking
    returns `llm_not_configured`). Makes no network call."""
    if settings.gemini_api_key is None:
        return None
    return GeminiClient(
        api_key=settings.gemini_api_key.get_secret_value(),
        model=settings.gemini_model_answer,
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_max_output_tokens,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        limiter=TokenBucket(settings.gemini_rpm_limit),
    )
