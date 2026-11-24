"""The LLM layer: provider interface, Gemini and Groq clients, the fallback chain, the rate
limiter, prompt templates (§4.7)."""

from __future__ import annotations

from app.core.config import Settings
from app.services.llm.base import LLMProvider, LLMResult
from app.services.llm.fallback import FallbackLLM
from app.services.llm.gemini import GeminiClient
from app.services.llm.groq import GroqClient
from app.services.llm.rate_limiter import TokenBucket

__all__ = [
    "FallbackLLM",
    "GeminiClient",
    "GroqClient",
    "LLMProvider",
    "LLMResult",
    "TokenBucket",
    "build_chain",
    "gemini_client",
    "build_llm",
]


def gemini_client(
    settings: Settings, model: str, shared: GeminiClient | None = None
) -> GeminiClient:
    """One Gemini model with its own rate limiter (also used by the evaluation for its judge)."""
    return GeminiClient(
        api_key=settings.gemini_api_key.get_secret_value(),
        model=model,
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_max_output_tokens,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        limiter=TokenBucket(settings.gemini_rpm_limit),  # per model: quotas are per model
        shared=shared,
    )


def build_chain(settings: Settings) -> list[LLMProvider]:
    """The configured models, in fallback order (D80): GEMINI_MODEL_ANSWER, GEMINI_MODEL_FALLBACK
    (same key), Groq (GROQ_API_KEY). Makes no network call."""
    chain: list[LLMProvider] = []
    if settings.gemini_api_key is not None:
        primary = gemini_client(settings, settings.gemini_model_answer)
        chain.append(primary)
        backup = settings.gemini_model_fallback
        if backup and backup != settings.gemini_model_answer:
            chain.append(gemini_client(settings, backup, shared=primary))
    if settings.groq_api_key is not None and settings.groq_model:
        chain.append(
            GroqClient(
                api_key=settings.groq_api_key.get_secret_value(),
                model=settings.groq_model,
                temperature=settings.llm_temperature,
                max_output_tokens=settings.llm_max_output_tokens,
                timeout_seconds=settings.llm_timeout_seconds,
                max_retries=settings.llm_max_retries,
                limiter=TokenBucket(settings.groq_rpm_limit),
            )
        )
    return chain


def build_llm(settings: Settings) -> LLMProvider | None:
    """The answer model with its fallbacks, or None when no LLM key is set (search keeps
    working; asking returns `llm_not_configured`). Makes no network call."""
    chain = build_chain(settings)
    if not chain:
        return None
    return chain[0] if len(chain) == 1 else FallbackLLM(chain)
