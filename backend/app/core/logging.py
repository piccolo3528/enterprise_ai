"""Log format for the whole backend: every line carries the ID of the request that produced it.

Example:
    2026-11-06 14:02:11 INFO  app.request [3f9c0a1b2d4e] GET /api/health -> 200 in 312 ms

The request ID is kept in a ContextVar: a per-request "global" that stays correct when many
requests run concurrently (each request's code sees only its own value).
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

LOG_FORMAT = "%(asctime)s %(levelname)-5s %(name)s [%(request_id)s] %(message)s"


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level)
    # Replace our handler on re-configuration (uvicorn --reload, tests) instead of stacking copies.
    for handler in [h for h in root.handlers if getattr(h, "_eki", False)]:
        root.removeHandler(handler)
    handler = logging.StreamHandler()
    handler._eki = True  # marks the handler as ours
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    handler.addFilter(RequestIdFilter())
    root.addHandler(handler)

    # Our middleware logs each request with its ID and duration, so uvicorn's access line
    # would be a duplicate. Third-party HTTP clients log every call at INFO; keep them quiet.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
