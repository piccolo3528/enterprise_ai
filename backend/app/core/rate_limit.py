"""Per-user and per-address request limits (M16), written by hand: a sliding-window log.

Why not the LLM token bucket (`services/llm/rate_limiter.py`)? That one paces *our* calls to
Gemini for everyone together and makes requests wait. These limits are about *who* asks: one
user (or one address) may not use up the shared free quota or the upload disk, and a password
can't be guessed at speed. Over a limit, the request is refused at once with 429 and
`Retry-After`; nothing waits.

**Sliding-window log.** Each key (a user id, an email, an address) keeps the times of its recent
events in a deque. An event is allowed if fewer than `limit` happened in the last `window`
seconds; `Retry-After` is when the oldest of them leaves the window. Exact (no burst at a window
boundary, unlike fixed per-minute counters), and memory is at most `limit` timestamps per key.

**In memory, one process** (no Redis, a project rule). Counts reset when the server restarts and
aren't shared between worker processes; the app runs as one uvicorn process (ARCHITECTURE
section 8.1), so that is the deployment this protects. A shared store (PostgreSQL rows, Redis) is
the upgrade if it ever runs several workers.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import RateLimitedError

MINUTE, HOUR, DAY = 60.0, 3600.0, 86400.0
LOGIN_WINDOW = 15 * MINUTE


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def describe_wait(seconds: float) -> str:
    """'40 seconds', '3 minutes', 'about 5 hours': for messages people read."""
    if seconds < 90:
        return f"{max(1, math.ceil(seconds))} seconds"
    if seconds < 90 * MINUTE:
        return f"{math.ceil(seconds / MINUTE)} minutes"
    return f"about {round(seconds / HOUR)} hours"


class SlidingWindowLimiter:
    """At most `limit` events per key in any `window` seconds. Thread-safe: `def` routes run in
    worker threads."""

    def __init__(
        self, limit: int, window: float, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        if limit < 1 or window <= 0:
            raise ValueError("limit must be >= 1 and window > 0")
        self.limit, self.window, self._clock = limit, window, clock
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._calls = 0

    def _recent(self, key: str, now: float) -> deque[float]:
        events = self._events.setdefault(key, deque())
        while events and events[0] <= now - self.window:
            events.popleft()
        return events

    def _sweep(self, now: float) -> None:
        """Drop keys with no recent events, so one-off keys (emails tried once) don't pile up."""
        for key in [k for k, ev in self._events.items() if not ev or ev[-1] <= now - self.window]:
            del self._events[key]

    def retry_after(self, key: str) -> float | None:
        """Seconds until one more event is allowed, or None if it is allowed now."""
        with self._lock:
            now = self._clock()
            events = self._recent(key, now)
            if len(events) < self.limit:
                return None
            return events[0] + self.window - now

    def hit(self, key: str) -> float | None:
        """Record an event if allowed. Returns None, or the wait in seconds if refused (and
        then records nothing: refused attempts don't extend the lock-out)."""
        with self._lock:
            now = self._clock()
            self._calls += 1
            if self._calls % 1000 == 0:
                self._sweep(now)
            events = self._recent(key, now)
            if len(events) >= self.limit:
                return events[0] + self.window - now
            events.append(now)
            return None

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def count(self, key: str) -> int:
        with self._lock:
            return len(self._recent(key, self._clock()))


@dataclass
class RateLimits:
    """Every limit the API applies, built once per app (`app.state.limits`)."""

    chat_minute: SlidingWindowLimiter
    chat_day: SlidingWindowLimiter
    uploads: SlidingWindowLimiter
    login_email: SlidingWindowLimiter  # failed sign-ins per email
    login_address: SlidingWindowLimiter  # failed sign-ins per client address
    registrations: SlidingWindowLimiter  # new accounts per client address

    @classmethod
    def from_settings(
        cls, settings: Settings, *, clock: Callable[[], float] = time.monotonic
    ) -> RateLimits:
        def limiter(limit: int, window: float) -> SlidingWindowLimiter:
            return SlidingWindowLimiter(limit, window, clock=clock)

        return cls(
            chat_minute=limiter(settings.rate_limit_chat_per_minute, MINUTE),
            chat_day=limiter(settings.rate_limit_chat_per_day, DAY),
            uploads=limiter(settings.rate_limit_uploads_per_hour, HOUR),
            login_email=limiter(settings.rate_limit_login_failures_per_email, LOGIN_WINDOW),
            login_address=limiter(settings.rate_limit_login_failures_per_address, LOGIN_WINDOW),
            registrations=limiter(settings.rate_limit_registrations_per_hour, HOUR),
        )

    # --- the checks the routes call --------------------------------------------------------

    def question(self, user_id: str) -> None:
        """One chat question (`/ask`, a new conversation, a follow-up). Both windows must allow
        it; the day is checked first so a refused question doesn't use a minute slot."""
        wait = self.chat_day.retry_after(user_id)
        if wait is not None:
            raise RateLimitedError(
                f"You've reached the limit of {_count(self.chat_day.limit, 'question')} in 24 "
                f"hours. Try again in {describe_wait(wait)}.",
                retry_after=wait,
            )
        wait = self.chat_minute.hit(user_id)
        if wait is not None:
            raise RateLimitedError(
                f"That's {_count(self.chat_minute.limit, 'question')} in a minute. "
                f"Try again in {describe_wait(wait)}.",
                retry_after=wait,
            )
        self.chat_day.hit(user_id)

    def upload(self, user_id: str) -> None:
        wait = self.uploads.hit(user_id)
        if wait is not None:
            raise RateLimitedError(
                f"You've uploaded {_count(self.uploads.limit, 'file')} in the last hour. "
                f"Try again in {describe_wait(wait)}.",
                retry_after=wait,
            )

    def check_login(self, email: str, address: str) -> None:
        """Before checking the password: refuse while either key is locked out. The message
        is the same whether or not the email has an account."""
        waits = [
            w
            for w in (self.login_email.retry_after(email), self.login_address.retry_after(address))
            if w is not None
        ]
        if waits:
            wait = max(waits)
            raise RateLimitedError(
                f"Too many failed sign-in attempts. Try again in {describe_wait(wait)}.",
                retry_after=wait,
            )

    def login_failed(self, email: str, address: str) -> None:
        self.login_email.hit(email)
        self.login_address.hit(address)

    def login_succeeded(self, email: str) -> None:
        """The right password clears that email's failures (not the address's: one person
        guessing many accounts from one address stays limited)."""
        self.login_email.reset(email)

    def registration(self, address: str) -> None:
        wait = self.registrations.hit(address)
        if wait is not None:
            raise RateLimitedError(
                f"Too many new accounts from this network. Try again in {describe_wait(wait)}.",
                retry_after=wait,
            )
