"""What the RAG code needs from an LLM, and nothing provider-specific (ARCHITECTURE §4.7).

The RAG pipeline depends on this interface only, so a fallback provider (Groq, D22), a paid tier
or a local model can be swapped in without touching it, and tests pass a fake.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    # "stop" (finished normally) or "max_tokens" (cut off at LLM_MAX_OUTPUT_TOKENS)
    finish_reason: str
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    attempts: int = 1  # 1 = no retry was needed
    # rate_limit_wait, generate; streamed calls add first_token (time to the first text)
    timings_ms: dict[str, float] = field(default_factory=dict)


class LLMProvider(Protocol):
    model: str

    def generate(
        self,
        *,
        system: str,
        prompt: str,
        model: str | None = None,
        json_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
    ) -> LLMResult:
        """One complete (non-streamed) answer. `model` overrides the default (the rewrite uses
        the utility model); `json_schema` asks for JSON matching that schema (the caller still
        validates it). Raises the LLM errors of `app.core.errors`: RateLimitedError,
        QuotaExhaustedError, LLMNotConfiguredError, LLMUnavailableError, AnswerBlockedError."""
        ...

    def stream(self, *, system: str, prompt: str) -> Iterator[str | LLMResult]:
        """The answer as it is generated: text pieces (str), then one final LLMResult with the
        whole text, finish reason and usage. Errors before the first piece are retried like
        `generate`; once text has been produced an error is raised as is (it can't be taken
        back). Closing the iterator early stops the generation."""
        ...
