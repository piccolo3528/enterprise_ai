"""The fallback chain (M15, D80): try each model in order until one answers.

    gemini-3.5-flash-lite (GEMINI_MODEL_ANSWER) → gemini-3.5-flash (GEMINI_MODEL_FALLBACK, same key,
    its own free quota) → Groq (GROQ_MODEL, another company: covers a Google outage too)

- **When it moves on:** the daily quota is used up, the provider is unavailable after its own
  retries, the per-minute limit couldn't be waited out, or it isn't configured. Not for a safety
  block: another model shouldn't be used to get around one.
- **Only before any text:** `stream()` switches only if the first piece never arrived; once the
  reader has seen text, a failure is reported as it is (an answer can't be stitched from two
  models).
- **A spent daily quota is skipped** for COOLDOWN_SECONDS, so every question doesn't pay a
  wasted call and its delay first.
- **Model overrides** (the planning call asks for GEMINI_MODEL_UTILITY) apply to the first
  provider only; backups use their own model.
- Results from a backup carry `fallback=True`; rag.py turns that into a notice on the answer.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import replace
from typing import Any

from app.core.errors import (
    LLMNotConfiguredError,
    LLMUnavailableError,
    QuotaExhaustedError,
    RateLimitedError,
)
from app.services.llm.base import LLMProvider, LLMResult

logger = logging.getLogger("app.llm")

COOLDOWN_SECONDS = 15 * 60
MOVE_ON = (QuotaExhaustedError, LLMUnavailableError, RateLimitedError, LLMNotConfiguredError)


class FallbackLLM:
    def __init__(
        self,
        providers: Sequence[LLMProvider],
        *,
        clock: Callable[[], float] = time.monotonic,
        cooldown: float = COOLDOWN_SECONDS,
    ) -> None:
        if not providers:
            raise ValueError("at least one provider")
        self.providers = list(providers)
        self.model = self.providers[0].model
        self._clock = clock
        self._cooldown = cooldown
        self._spent_until: dict[int, float] = {}
        self._lock = threading.Lock()

    def sdk(self) -> Any:
        """Startup warm-up: build every Gemini SDK client (the backups share the first one's)."""
        for provider in self.providers:
            if callable(getattr(provider, "sdk", None)):
                provider.sdk()

    def _order(self) -> list[tuple[int, LLMProvider]]:
        now = self._clock()
        with self._lock:
            ready = [(i, p) for i, p in enumerate(self.providers)
                     if self._spent_until.get(i, 0.0) <= now]  # fmt: skip
        return ready or list(enumerate(self.providers))  # all spent: try them all anyway

    def _failed(self, index: int, exc: Exception) -> None:
        name = self.providers[index].model
        logger.warning("LLM %s failed (%s); trying the next model", name, getattr(exc, "code", exc))
        if isinstance(exc, QuotaExhaustedError):
            with self._lock:
                self._spent_until[index] = self._clock() + self._cooldown

    def generate(self, *, system: str, prompt: str, model: str | None = None,
                 json_schema: dict[str, Any] | None = None,
                 max_output_tokens: int | None = None) -> LLMResult:  # fmt: skip
        last: Exception | None = None
        for index, provider in self._order():
            try:
                result = provider.generate(
                    system=system, prompt=prompt, model=model if index == 0 else None,
                    json_schema=json_schema, max_output_tokens=max_output_tokens,
                )  # fmt: skip
            except MOVE_ON as exc:
                self._failed(index, exc)
                last = exc
                continue
            return replace(result, fallback=index > 0)
        raise last  # type: ignore[misc]

    def stream(self, *, system: str, prompt: str) -> Iterator[str | LLMResult]:
        last: Exception | None = None
        for index, provider in self._order():
            pieces = provider.stream(system=system, prompt=prompt)
            try:
                first = next(pieces)
            except MOVE_ON as exc:
                pieces.close()
                self._failed(index, exc)
                last = exc
                continue
            except StopIteration:
                last = LLMUnavailableError("The AI service returned an empty answer.")
                continue
            try:
                for piece in _chain(first, pieces):
                    if isinstance(piece, LLMResult):
                        piece = replace(piece, fallback=index > 0)
                    yield piece
            finally:
                pieces.close()
            return
        raise last  # type: ignore[misc]


def _chain(first: Any, rest: Iterator[Any]) -> Iterator[Any]:
    yield first
    yield from rest
