"""What the RAG code needs from an LLM, and nothing provider-specific (ARCHITECTURE §4.7).

The RAG pipeline depends on this interface only, so a fallback provider (Groq, D22), a paid tier
or a local model can be swapped in without touching it, and tests pass a fake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    # "stop" (finished normally) or "max_tokens" (cut off at LLM_MAX_OUTPUT_TOKENS)
    finish_reason: str
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    attempts: int = 1  # 1 = no retry was needed
    timings_ms: dict[str, float] = field(default_factory=dict)  # rate_limit_wait, generate


class LLMProvider(Protocol):
    model: str

    def generate(self, *, system: str, prompt: str) -> LLMResult:
        """One complete (non-streamed) answer. Raises the LLM errors of `app.core.errors`:
        RateLimitedError, QuotaExhaustedError, LLMNotConfiguredError, LLMUnavailableError,
        AnswerBlockedError."""
        ...
