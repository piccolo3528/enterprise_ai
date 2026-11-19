"""A token bucket, written by hand: our side of the LLM provider's requests-per-minute limit.

The bucket holds up to `burst` tokens and refills at `rate_per_minute / 60` tokens per second.
Each request takes one token. With none left, the request *waits* for the next one, unless that
would take longer than `max_wait`, in which case it fails fast with a "rate limited" error
instead of hanging the user's request.

Why have it at all, when Google returns 429 anyway? A 429 costs a round trip, and the free tier
counts rejected requests too. Pacing on our side turns a burst of questions into short waits
instead of errors. The server's 429 stays the backstop: Google counts per project, so another
process using the same key (the evaluation, a script) isn't visible here.

**Reservations keep it fair.** A request takes its token *before* sleeping, so the count may go
negative: -1.5 means "1.5 tokens are already promised to earlier callers". The next caller's
wait is computed from that, so requests are served in arrival order. A plain lock-and-retry loop
would let a late request overtake one that has been waiting.

**Burst vs. strictness.** In any 60-second window at most `burst + rate_per_minute` requests
start, so burst=2 at 10 RPM can mean 12 in a minute; the server's 429 handles that edge. burst=1
would be strict but makes even two simultaneous questions wait (6 s at 10 RPM).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from app.core.errors import RateLimitedError

RATE_LIMITED = "Too many questions in a short time. Please wait a few seconds and try again."


class TokenBucket:
    def __init__(
        self,
        rate_per_minute: float,
        *,
        burst: int = 2,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate_per_minute <= 0 or burst < 1:
            raise ValueError("rate_per_minute must be > 0 and burst >= 1")
        self.rate = rate_per_minute / 60.0  # tokens per second
        self.capacity = float(burst)
        self._tokens = float(burst)
        self._clock = clock
        self._sleep = sleep
        self._updated = clock()
        self._lock = threading.Lock()

    def _refill(self, now: float) -> None:
        self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.rate)
        self._updated = now

    def reserve(self, max_wait: float) -> float:
        """Take a token; return how many seconds the caller must wait before using it.
        Raises RateLimitedError (and takes nothing) if that is longer than `max_wait`."""
        with self._lock:
            self._refill(self._clock())
            # The epsilon absorbs float error: at 10 RPM, 6 s of refill is 0.9999999999999999.
            wait = 0.0 if self._tokens >= 1 - 1e-9 else (1 - self._tokens) / self.rate
            if wait > max_wait:
                raise RateLimitedError(RATE_LIMITED, retry_after=wait)
            self._tokens -= 1
            return wait

    def acquire(self, max_wait: float) -> float:
        """Take a token, sleeping until it's due (outside the lock). Returns the seconds waited."""
        wait = self.reserve(max_wait)
        if wait > 0:
            self._sleep(wait)
        return wait
