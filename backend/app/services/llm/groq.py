"""Groq through its OpenAI-compatible REST API: the last step of the fallback chain (D80).

No SDK: one POST to /chat/completions (streamed or not) with httpx, which is already installed.
Same contract as GeminiClient (`generate`, `stream`, the same error types), so the fallback chain
and the RAG code don't care which provider answered.

- **TLS through the OS trust store.** httpx's default CA bundle doesn't include the certificate a
  corporate TLS-inspecting gateway re-signs traffic with; `ssl.create_default_context()` reads the
  Windows store, which does. Verification stays on.
- **Limits (free tier, measured 2026-11-23):** 1,000 requests a day and 8,000 tokens a minute per
  model. Tokens per minute bind first (an answer prompt is ~3.6k tokens), so a 429 waits the
  server's `retry-after` (≤ 20 s) within the same 60 s deadline as Gemini.
- **Daily limits** (requests or tokens per day) are `quota_exhausted`, not retried; the fallback
  chain then has nothing left and the user sees that error.
- **JSON mode:** `response_format = json_object`, with the schema described in the system prompt
  (the caller validates the reply, as for Gemini).
- **Reasoning models** (gpt-oss) think before answering, and those tokens count against
  `max_tokens`: `reasoning_effort` is kept low and the cap gets headroom for it.

Neither the prompt nor the answer is logged.
"""

from __future__ import annotations

import json
import logging
import random
import ssl
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx

from app.core.errors import (
    AppError,
    LLMNotConfiguredError,
    LLMUnavailableError,
    QuotaExhaustedError,
    RateLimitedError,
)
from app.services.llm.base import LLMResult
from app.services.llm.rate_limiter import RATE_LIMITED, TokenBucket

logger = logging.getLogger("app.llm")

URL = "https://api.groq.com/openai/v1/chat/completions"
DEADLINE_SECONDS = 60.0
LIMITER_MAX_WAIT = 10.0
MAX_SERVER_DELAY = 20.0
REASONING_HEADROOM = 1024  # extra output tokens for a reasoning model's thinking

QUOTA_EXHAUSTED = "The backup AI service's daily free quota is used up too. Please try again later."
NOT_CONFIGURED = "The backup AI service isn't set up correctly: check GROQ_API_KEY and GROQ_MODEL."
UNAVAILABLE = "The backup AI service isn't responding right now. Please try again in a minute."
EMPTY = "The backup AI service returned an empty answer. Please try again."


def classify(status: int, body: str, headers) -> tuple[AppError, bool, float | None]:
    """(error, retryable?, server delay) for a failed HTTP response."""
    message = body.lower()
    if status == 429:
        if "per day" in message or "(rpd)" in message or "(tpd)" in message:
            return QuotaExhaustedError(QUOTA_EXHAUSTED), False, None
        try:
            delay = float(headers.get("retry-after", ""))
        except ValueError:
            delay = None
        return RateLimitedError(RATE_LIMITED, retry_after=delay), True, delay
    if status in (401, 403, 404):
        return LLMNotConfiguredError(NOT_CONFIGURED), False, None
    if status >= 500:
        return LLMUnavailableError(UNAVAILABLE), True, None
    return LLMUnavailableError(UNAVAILABLE), False, None  # 400/413/422: our request is wrong


class GroqClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        temperature: float,
        max_output_tokens: int,
        timeout_seconds: float,
        max_retries: int,
        limiter: TokenBucket,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._limiter = limiter
        self._clock = clock
        self._sleep = sleep
        self._http = httpx.Client(
            transport=transport,
            verify=ssl.create_default_context() if transport is None else True,
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": "eki-backend"},
        )

    def _body(self, system: str, prompt: str, *, json_schema, max_output_tokens, stream) -> dict:
        if json_schema:
            system += ("\n\nReply with one JSON object matching this JSON Schema, and nothing "
                       f"else:\n{json.dumps(json_schema)}")  # fmt: skip
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "max_completion_tokens": (max_output_tokens or self.max_output_tokens)
            + (REASONING_HEADROOM if self._reasoning else 0),
            "stream": stream,
        }
        if self._reasoning:
            body["reasoning_effort"] = "low"
        if json_schema:
            body["response_format"] = {"type": "json_object"}
        if stream:
            body["stream_options"] = {"include_usage": True}
        return body

    @property
    def _reasoning(self) -> bool:
        return "gpt-oss" in self.model

    def _send(self, body: dict, *, stream: bool) -> tuple[httpx.Response, int, float, float]:
        """POST with pacing and retries (before any text). Returns (response, attempts,
        seconds waited for the limiter, start of the successful attempt)."""
        started, waited, attempt = self._clock(), 0.0, 0
        while True:
            attempt += 1
            remaining = DEADLINE_SECONDS - (self._clock() - started)
            waited += self._limiter.acquire(max_wait=min(LIMITER_MAX_WAIT, max(0.0, remaining)))
            t = self._clock()
            try:
                request = self._http.build_request("POST", URL, json=body)
                response = self._http.send(request, stream=stream)
            except httpx.TransportError as exc:
                error, retryable, delay = LLMUnavailableError(UNAVAILABLE), True, None
                status = type(exc).__name__
            else:
                if response.status_code == 200:
                    return response, attempt, waited, t
                text = response.read().decode("utf-8", "replace")
                response.close()
                error, retryable, delay = classify(response.status_code, text, response.headers)
                status = response.status_code
            if not retryable or attempt > self.max_retries:
                logger.warning("Groq call failed (%s) after %d attempt(s)", status, attempt)
                raise error
            if delay is not None and delay > MAX_SERVER_DELAY:
                logger.warning("Groq asked to wait %.0f s: not retrying", delay)
                raise error
            wait = delay if delay is not None else random.random() * min(8.0, 2 ** (attempt - 1))
            if self._clock() - started + wait + self.timeout_seconds > DEADLINE_SECONDS:
                raise error
            logger.warning("Groq attempt %d failed (%s); retrying in %.1f s", attempt, status, wait)
            self._sleep(wait)

    def _ms_since(self, t: float) -> float:
        return round((self._clock() - t) * 1000, 1)

    def generate(
        self,
        *,
        system: str,
        prompt: str,
        model: str | None = None,  # ignored: a Groq client has one model
        json_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
    ) -> LLMResult:
        body = self._body(system, prompt, json_schema=json_schema,
                          max_output_tokens=max_output_tokens, stream=False)  # fmt: skip
        response, attempts, waited, t = self._send(body, stream=False)
        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        text = ((choice.get("message") or {}).get("content") or "").strip()
        if not text:
            raise LLMUnavailableError(EMPTY)
        usage = data.get("usage") or {}
        return LLMResult(
            text=text,
            model=data.get("model") or self.model,
            finish_reason="max_tokens" if choice.get("finish_reason") == "length" else "stop",
            prompt_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            attempts=attempts,
            timings_ms={"rate_limit_wait": round(waited * 1000, 1), "generate": self._ms_since(t)},
        )

    def stream(self, *, system: str, prompt: str) -> Iterator[str | LLMResult]:
        body = self._body(system, prompt, json_schema=None, max_output_tokens=None, stream=True)
        response, attempts, waited, t = self._send(body, stream=True)
        parts: list[str] = []
        finish, usage, first_token, model = "", {}, None, self.model
        try:
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                model = chunk.get("model") or model
                usage = chunk.get("usage") or (chunk.get("x_groq") or {}).get("usage") or usage
                for choice in chunk.get("choices") or []:
                    finish = choice.get("finish_reason") or finish
                    text = (choice.get("delta") or {}).get("content")
                    if text:
                        if first_token is None:
                            first_token = self._ms_since(t)
                        parts.append(text)
                        yield text
        except httpx.TransportError:
            logger.warning("Groq stream failed mid-answer")
            raise LLMUnavailableError(UNAVAILABLE) from None
        finally:
            response.close()
        text = "".join(parts).strip()
        if not text:
            raise LLMUnavailableError(EMPTY)
        yield LLMResult(
            text=text,
            model=model,
            finish_reason="max_tokens" if finish == "length" else "stop",
            prompt_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            attempts=attempts,
            timings_ms={
                "rate_limit_wait": round(waited * 1000, 1),
                "first_token": first_token or 0.0,
                "generate": self._ms_since(t),
            },
        )
