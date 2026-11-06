"""Service health checks for GET /api/health.

The database and Qdrant checks are independent network calls (~290 ms and ~260 ms from this
laptop), so they run concurrently: the endpoint takes about as long as the slower one, not the
sum. Both clients are synchronous, so each call runs in a worker thread (`asyncio.to_thread`)
and the event loop stays free to serve other requests meanwhile.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version

from qdrant_client import QdrantClient
from sqlalchemy import Engine

from app.core.config import Settings
from app.db import session as db_session
from app.schemas.health import (
    HealthReport,
    LlmInfo,
    ModelsInfo,
    ServiceCheck,
    Services,
    VectorStoreCheck,
)

logger = logging.getLogger(__name__)

# Long enough for Neon to wake from scale-to-zero (~5 s in M1), short enough that the status
# page never hangs for the full 30 s connect timeout.
CHECK_TIMEOUT_S = 15.0


def app_version() -> str:
    try:
        return version("enterprise-knowledge-intelligence")
    except PackageNotFoundError:
        return "0.0.0"


async def _run_check[T](name: str, fn: Callable[[], T]) -> tuple[T | None, float, str | None]:
    """Run a blocking check in a thread with a timeout. Returns (result, elapsed_ms, error)."""
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(asyncio.to_thread(fn), timeout=CHECK_TIMEOUT_S)
        return result, (time.perf_counter() - started) * 1000, None
    except TimeoutError:
        logger.warning("Health check %s: no response within %.0f s", name, CHECK_TIMEOUT_S)
        error = f"no response within {CHECK_TIMEOUT_S:.0f} s"
    except Exception as exc:  # noqa: BLE001 - a failed check is reported, never raised
        # Full message in the server log; only the exception type goes to the client, because
        # driver messages can contain host names and usernames.
        logger.warning("Health check %s failed: %s: %s", name, type(exc).__name__, exc)
        error = type(exc).__name__
    return None, (time.perf_counter() - started) * 1000, error


async def check_database(engine: Engine) -> ServiceCheck:
    _, elapsed_ms, error = await _run_check("database", lambda: db_session.ping(engine))
    if error:
        return ServiceCheck(status="error", latency_ms=round(elapsed_ms), detail=error)
    return ServiceCheck(status="ok", latency_ms=round(elapsed_ms))


async def check_vector_store(client: QdrantClient, collection: str) -> VectorStoreCheck:
    exists, elapsed_ms, error = await _run_check(
        "vector_store", lambda: client.collection_exists(collection)
    )
    if error:
        return VectorStoreCheck(
            status="error", latency_ms=round(elapsed_ms), detail=error, collection=collection
        )
    return VectorStoreCheck(
        status="ok", latency_ms=round(elapsed_ms), collection=collection, collection_exists=exists
    )


async def collect_health(engine: Engine, qdrant: QdrantClient, settings: Settings) -> HealthReport:
    database, vector_store = await asyncio.gather(
        check_database(engine), check_vector_store(qdrant, settings.qdrant_collection)
    )
    llm = LlmInfo(
        api_key_configured=settings.gemini_api_key is not None,
        answer_model=settings.gemini_model_answer,
        utility_model=settings.gemini_model_utility,
        fallback_configured=settings.groq_api_key is not None,
    )
    healthy = database.status == "ok" and vector_store.status == "ok" and llm.api_key_configured
    return HealthReport(
        status="ok" if healthy else "degraded",
        version=app_version(),
        services=Services(database=database, vector_store=vector_store, llm=llm),
        models=ModelsInfo(embedding=settings.embedding_model, reranker=settings.reranker_model),
    )
