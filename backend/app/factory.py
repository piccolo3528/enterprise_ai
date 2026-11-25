"""FastAPI application factory.

Kept separate from `app/main.py` so tests can build an app with their own settings without
importing the module that loads backend/.env.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from app.api.routes import (
    answers,
    auth,
    conversations,
    documents,
    health,
    knowledge_bases,
    search,
    stats,
)
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import RateLimits
from app.core.sessions import TokenVersions
from app.db.session import build_engine, build_read_session_factory, build_session_factory
from app.db.session import warm_up as warm_up_database
from app.services.embeddings import get_embedder
from app.services.health import app_version
from app.services.ingestion.pipeline import recover_interrupted
from app.services.ingestion.tokens import get_tokens
from app.services.llm import build_llm
from app.services.reranker import get_reranker
from app.services.vector_store import VectorStore, build_qdrant_client

logger = logging.getLogger("app")


async def _warm_up(name: str, fn: Callable[[], object]) -> None:
    started = time.perf_counter()
    try:
        await asyncio.to_thread(fn)
        logger.info("%s warmed up in %.2f s", name, time.perf_counter() - started)
    except Exception as exc:  # noqa: BLE001 - the app still starts; /api/health shows the problem
        logger.warning("%s warm-up failed (%s); requests will retry", name, type(exc).__name__)


async def _warm_up_services(
    app: FastAPI, embedding_model: str, started_at: datetime, reranker_model: str | None = None
) -> None:
    """Open the first Neon connection (~4-5 s), load the tokenizer and the embedding model
    (~25 s: importing PyTorch) concurrently, so none of it lands on a user's first request.
    Once the database is up, documents whose processing a restart interrupted are marked failed
    (retryable). Once the model is loaded, the Qdrant collection is created if missing (its
    dimension comes from the model)."""

    async def database() -> None:
        await _warm_up("Database pool", lambda: warm_up_database(app.state.engine))
        try:
            await asyncio.to_thread(recover_interrupted, app.state.session_factory, started_at)
        except Exception as exc:  # noqa: BLE001 - startup continues; logged for the developer
            logger.warning("Recovery of interrupted documents failed (%s)", type(exc).__name__)

    async def vectors() -> None:
        await _warm_up("Embedding model", lambda: get_embedder(embedding_model))
        await _warm_up(
            "Qdrant collection",
            lambda: app.state.vector_store.ensure_collection(
                get_embedder(embedding_model).dimension
            ),
        )

    tasks = [
        database(),
        vectors(),
        # ~5 s the first time; loaded now so the first upload doesn't wait for it.
        _warm_up("Tokenizer", lambda: get_tokens(embedding_model)),
    ]
    if reranker_model:  # only when RERANK_ENABLED (M14): ~2 s after the embedding model
        tasks.append(_warm_up("Reranker", lambda: get_reranker(reranker_model)))
    sdk = getattr(getattr(app.state, "llm", None), "sdk", None)
    if sdk is not None:  # ~10 s (SDK import + client); no network call, no quota
        tasks.append(_warm_up("Gemini client", sdk))
    await asyncio.gather(*tasks)


def create_app(settings: Settings | None = None, *, warm_up: bool = True) -> FastAPI:
    """Build the app. Tests pass their own settings and `warm_up=False` (no network)."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Startup: create shared clients once; every request reuses them.
        started_at = datetime.now(UTC)
        logger.info("Starting (configuration: %s)", settings.describe())
        app.state.engine = build_engine(settings.database_url.get_secret_value())
        app.state.session_factory = build_session_factory(app.state.engine)
        app.state.read_session_factory = build_read_session_factory(app.state.engine)
        app.state.qdrant = build_qdrant_client(settings)
        app.state.vector_store = VectorStore(app.state.qdrant, settings.qdrant_collection)
        app.state.llm = build_llm(settings)  # no network call; None without GEMINI_API_KEY
        # Warm-up runs in the background, so the server accepts requests immediately (and
        # `--reload` restarts stay fast). A request that arrives while the warm-up connection is
        # still busy opens a second connection of its own (~1.35 s): measured, not a bug.
        warm_task = (
            asyncio.create_task(
                _warm_up_services(
                    app,
                    settings.embedding_model,
                    started_at,
                    settings.reranker_model if settings.rerank_enabled else None,
                )
            )
            if warm_up
            else None
        )
        yield
        # Shutdown: release connections.
        if warm_task is not None and not warm_task.done():
            warm_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await warm_task
        app.state.qdrant.close()
        app.state.engine.dispose()
        logger.info("Stopped")

    app = FastAPI(
        title="Enterprise Knowledge Intelligence Platform",
        version=app_version(),
        lifespan=lifespan,
        docs_url="/docs" if settings.api_docs_enabled else None,
        redoc_url="/redoc" if settings.api_docs_enabled else None,
        openapi_url="/openapi.json" if settings.api_docs_enabled else None,
    )
    app.state.settings = settings
    app.state.limits = RateLimits.from_settings(settings)  # per-user limits, in memory (M16)
    app.state.token_versions = TokenVersions()  # sign out everywhere (M16, D83)
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(knowledge_bases.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(answers.router, prefix="/api")
    app.include_router(conversations.router, prefix="/api")
    app.include_router(stats.router, prefix="/api")
    return app
