"""Gemini through the `google-genai` SDK, with our own pacing, retries and error mapping (§4.7).

One call = acquire a rate-limiter token -> generate_content (or generate_content_stream) -> map
the outcome:

| What happened                          | Retry?                    | Error the user sees        |
|----------------------------------------|---------------------------|----------------------------|
| 429, per-minute quota                  | yes, after the server's   | `rate_limited` (429)       |
|                                        | RetryInfo delay if given  |                            |
| 429, per-day quota                     | no: it won't reset today  | `quota_exhausted` (429)    |
| 500 / 502 / 503 / 504, timeout,        | yes, exponential backoff  | `llm_unavailable` (503)    |
| network error                          | with full jitter          |                            |
| bad key (400 API_KEY_INVALID, 401,     | no                        | `llm_not_configured` (503) |
| 403), unknown model (404)              |                           |                            |
| safety block, empty answer             | no                        | `answer_blocked` (422) /   |
|                                        |                           | `llm_unavailable`          |

**The SDK's own retries are switched off** (`attempts=1`): it doesn't tell a per-minute 429 from a
per-day one, so it would retry a quota that can't recover today, and two retry layers multiply.

**Everything fits a deadline** (60 s): a retry starts only if its wait + a full attempt still fit,
so the request ends before the browser gives up (75 s for answers).

**Streaming (M13)** retries only until the first piece of text arrives: the SDK sends the request
when the stream is first read, so "open the stream and read one chunk" is the attempt. Once text
has reached the reader, a failure is reported as it is; retrying would repeat or contradict it.

Neither the prompt nor the answer is ever logged: both contain document text and the question.
"""

from __future__ import annotations

import importlib
import logging
import random
import re
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any, TypeVar

from app.core.errors import (
    AnswerBlockedError,
    AppError,
    LLMNotConfiguredError,
    LLMUnavailableError,
    QuotaExhaustedError,
    RateLimitedError,
)
from app.services.llm.base import LLMResult
from app.services.llm.rate_limiter import RATE_LIMITED, TokenBucket

logger = logging.getLogger("app.llm")

T = TypeVar("T")

DEADLINE_SECONDS = 60.0  # the whole call, retries included
LIMITER_MAX_WAIT = 10.0  # longer than this in our own queue -> rate_limited right away
MAX_SERVER_DELAY = 20.0  # a 429 asking us to wait longer than this isn't retried
BACKOFF_BASE = 1.0
BACKOFF_CAP = 8.0

QUOTA_EXHAUSTED = (
    "The AI service's daily free quota is used up. It resets at midnight Pacific time; "
    "search still works meanwhile."
)
NOT_CONFIGURED = (
    "AI answers aren't set up correctly on this server: check GEMINI_API_KEY and "
    "GEMINI_MODEL_ANSWER in backend/.env."
)
UNAVAILABLE = "The AI service isn't responding right now. Please try again in a minute."
TIMED_OUT = "The AI service took too long to answer. Please try again."
BLOCKED = "The AI service declined to answer this question (blocked by its safety filter)."
EMPTY = "The AI service returned an empty answer. Please try again."

_BLOCKED_FINISH = {
    "SAFETY", "RECITATION", "LANGUAGE", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII",
}  # fmt: skip
_RETRYABLE_STATUS = {500, 502, 503, 504}
_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)s\s*$")


def _transport_errors() -> tuple[type[BaseException], ...]:
    """Network failures and timeouts. The SDK may use httpx or its successor httpx2, whose
    exception classes are different types, so both are collected."""
    classes = []
    for name in ("httpx", "httpx2"):
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        if cls := getattr(module, "TransportError", None):
            classes.append(cls)
    return tuple(classes)


_TRANSPORT_ERRORS = _transport_errors()


def _error_details(body: Any) -> list[dict]:
    """The `details` list of a Google API error body: {"error": {"details": [...]}}."""
    if isinstance(body, dict):
        body = body.get("error", body)
        details = body.get("details") if isinstance(body, dict) else None
        if isinstance(details, list):
            return [d for d in details if isinstance(d, dict)]
    return []


def retry_delay(body: Any) -> float | None:
    """Seconds from a google.rpc.RetryInfo detail ("retryDelay": "39s"), if present."""
    for detail in _error_details(body):
        if str(detail.get("@type", "")).endswith("RetryInfo"):
            match = _DURATION.match(str(detail.get("retryDelay", "")))
            if match:
                return float(match.group(1))
    return None


def is_daily_quota(body: Any) -> bool:
    """True if a 429's QuotaFailure names a per-day quota (e.g. "...PerDayPerProject...")."""
    for detail in _error_details(body):
        if str(detail.get("@type", "")).endswith("QuotaFailure"):
            for violation in detail.get("violations") or []:
                quota = f"{violation.get('quotaId', '')} {violation.get('quotaMetric', '')}"
                if "perday" in quota.lower().replace("_", ""):
                    return True
    return False


def _mentions_api_key(exc: Any) -> bool:
    text = f"{getattr(exc, 'message', '')} {getattr(exc, 'details', '')}"
    return "API_KEY_INVALID" in text or "API key" in text


def classify(exc: BaseException) -> tuple[AppError, bool, float | None]:
    """(error to raise, retryable?, server-requested delay) for one failed attempt.
    Anything unrecognised is re-raised by the caller: a bug should show up as a 500 with a
    traceback in the log, not hide behind "try again later"."""
    from google.genai import errors  # the SDK is imported lazily, like the other models

    if isinstance(exc, _TRANSPORT_ERRORS):
        timed_out = "Timeout" in type(exc).__name__
        return LLMUnavailableError(TIMED_OUT if timed_out else UNAVAILABLE), True, None
    if isinstance(exc, errors.APIError):
        code = exc.code
        if code == 429:
            if is_daily_quota(exc.details):
                return QuotaExhaustedError(QUOTA_EXHAUSTED), False, None
            delay = retry_delay(exc.details)
            return RateLimitedError(RATE_LIMITED, retry_after=delay), True, delay
        if code in _RETRYABLE_STATUS:
            return LLMUnavailableError(UNAVAILABLE), True, None
        if code in (401, 403, 404) or (code == 400 and _mentions_api_key(exc)):
            return LLMNotConfiguredError(NOT_CONFIGURED), False, None
        return LLMUnavailableError(UNAVAILABLE), False, None  # another 4xx: our request is wrong
    raise exc


class GeminiClient:
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
        client: Any = None,
        shared: GeminiClient | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._limiter = limiter
        self._clock = clock
        self._sleep = sleep
        self._jitter = jitter
        self._api_key = api_key
        self._client = client
        # Another model on the same key (the fallback chain) reuses that client's SDK client:
        # building one costs 5-6 s and holds HTTP connections (D64).
        self._shared = shared
        self._lock = threading.Lock()

    def sdk(self) -> Any:
        """The SDK client, built on first use. Measured: importing the SDK takes ~4 s and *each*
        `genai.Client(...)` ~5-6 s (no network call; it sets up its HTTP clients), which made
        every app start, and every test that starts the app, 7-10 s slower. The server's
        background warm-up calls this, so the first question doesn't wait either."""
        with self._lock:
            if self._client is None and self._shared is not None:
                self._client = self._shared.sdk()
            if self._client is None:
                from google import genai
                from google.genai import types

                self._client = genai.Client(
                    api_key=self._api_key,  # sent in a request header, never logged
                    http_options=types.HttpOptions(
                        timeout=int(self.timeout_seconds * 1000),  # milliseconds
                        retry_options=types.HttpRetryOptions(attempts=1),  # we retry ourselves
                    ),
                )
            return self._client

    def _config(
        self,
        system: str,
        *,
        json_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
    ):
        from google.genai import types

        return types.GenerateContentConfig(
            system_instruction=system,
            temperature=self.temperature,
            max_output_tokens=max_output_tokens or self.max_output_tokens,
            candidate_count=1,
            # We never pass tools, so the SDK's automatic function calling has nothing to do; off,
            # it also stops logging "AFC is enabled" on every call.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            response_mime_type="application/json" if json_schema else None,
            response_json_schema=json_schema,
        )

    def backoff(self, attempt: int) -> float:
        """Full jitter: a random wait in [0, min(cap, base * 2^(attempt-1))]. Randomness spreads
        clients that failed together, so they don't all retry in the same instant."""
        return self._jitter() * min(BACKOFF_CAP, BACKOFF_BASE * 2 ** (attempt - 1))

    def _with_retries(self, call: Callable[[], T]) -> tuple[T, int, float, float]:
        """Run `call` paced by the limiter and retried per the table above, within the deadline.
        Returns (its result, attempts, seconds waited for the limiter, start of the attempt that
        succeeded)."""
        started = self._clock()
        waited = 0.0
        attempt = 0
        while True:
            attempt += 1
            remaining = DEADLINE_SECONDS - (self._clock() - started)
            waited += self._limiter.acquire(max_wait=min(LIMITER_MAX_WAIT, max(0.0, remaining)))
            t = self._clock()
            try:
                return call(), attempt, waited, t
            except Exception as exc:  # noqa: BLE001 - classify() re-raises what it doesn't know
                error, retryable, server_delay = classify(exc)
                status = getattr(exc, "code", None) or type(exc).__name__
                if not retryable or attempt > self.max_retries:
                    logger.warning("Gemini call failed (%s) after %d attempt(s)", status, attempt)
                    raise error from None
                delay = self.backoff(attempt)
                if server_delay is not None:
                    if server_delay > MAX_SERVER_DELAY:
                        logger.warning("Gemini asked to wait %.0f s: not retrying", server_delay)
                        raise error from None
                    delay = max(delay, server_delay)
                elapsed = self._clock() - started
                if elapsed + delay + self.timeout_seconds > DEADLINE_SECONDS:
                    logger.warning("Gemini call failed (%s): no time left to retry", status)
                    raise error from None
                logger.warning(
                    "Gemini attempt %d failed (%s); retrying in %.1f s", attempt, status, delay
                )
                self._sleep(delay)

    def _ms_since(self, t: float) -> float:
        return round((self._clock() - t) * 1000, 1)

    def generate(
        self,
        *,
        system: str,
        prompt: str,
        model: str | None = None,
        json_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
    ) -> LLMResult:
        name = model or self.model
        config = self._config(system, json_schema=json_schema, max_output_tokens=max_output_tokens)
        response, attempts, waited, t = self._with_retries(
            lambda: self.sdk().models.generate_content(model=name, contents=prompt, config=config)
        )
        timings = {"rate_limit_wait": round(waited * 1000, 1), "generate": self._ms_since(t)}
        return self._to_result(response, attempts, timings, name)

    def stream(self, *, system: str, prompt: str) -> Iterator[str | LLMResult]:
        config = self._config(system)

        def open_stream():
            chunks = self.sdk().models.generate_content_stream(
                model=self.model, contents=prompt, config=config
            )
            return chunks, next(chunks, None)  # the request is sent here

        (chunks, chunk), attempts, waited, t = self._with_retries(open_stream)
        parts: list[str] = []
        reason_name = ""
        usage = None
        model_version = None
        first_token = None
        try:
            while chunk is not None:
                feedback = getattr(chunk, "prompt_feedback", None)
                if feedback is not None and getattr(feedback, "block_reason", None):
                    raise AnswerBlockedError(BLOCKED)
                candidates = getattr(chunk, "candidates", None) or []
                if candidates and candidates[0].finish_reason:
                    reason = candidates[0].finish_reason
                    reason_name = getattr(reason, "name", str(reason))
                    if reason_name in _BLOCKED_FINISH:
                        raise AnswerBlockedError(BLOCKED)
                usage = getattr(chunk, "usage_metadata", None) or usage
                model_version = getattr(chunk, "model_version", None) or model_version
                text = chunk.text if candidates else None
                if text:
                    if first_token is None:
                        first_token = self._ms_since(t)
                    parts.append(text)
                    yield text
                try:
                    chunk = next(chunks, None)
                except Exception as exc:  # noqa: BLE001 - classify() re-raises what it doesn't know
                    error, _, _ = classify(exc)
                    status = getattr(exc, "code", None) or type(exc).__name__
                    logger.warning("Gemini stream failed mid-answer (%s)", status)
                    raise error from None
        finally:
            chunks.close()  # also when the reader stops early: ends the HTTP response
        text = "".join(parts).strip()
        if not text:
            raise LLMUnavailableError(EMPTY)
        timings = {
            "rate_limit_wait": round(waited * 1000, 1),
            "first_token": first_token or 0.0,
            "generate": self._ms_since(t),
        }
        yield LLMResult(
            text=text,
            model=model_version or self.model,
            finish_reason="max_tokens" if reason_name == "MAX_TOKENS" else "stop",
            prompt_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
            attempts=attempts,
            timings_ms=timings,
        )

    def _to_result(
        self, response: Any, attempts: int, timings: dict[str, float], model: str
    ) -> LLMResult:
        feedback = getattr(response, "prompt_feedback", None)
        if feedback is not None and getattr(feedback, "block_reason", None):
            raise AnswerBlockedError(BLOCKED)
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            raise LLMUnavailableError(EMPTY)
        reason = candidates[0].finish_reason
        reason_name = getattr(reason, "name", str(reason or ""))
        if reason_name in _BLOCKED_FINISH:
            raise AnswerBlockedError(BLOCKED)
        text = (response.text or "").strip()
        if not text:
            raise LLMUnavailableError(EMPTY)
        usage = getattr(response, "usage_metadata", None)
        return LLMResult(
            text=text,
            model=getattr(response, "model_version", None) or model,
            finish_reason="max_tokens" if reason_name == "MAX_TOKENS" else "stop",
            prompt_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
            attempts=attempts,
            timings_ms=timings,
        )
