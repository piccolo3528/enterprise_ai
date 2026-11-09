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

from fastapi import FastAPI

from app.api.routes import health
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.db.session import build_engine, build_read_session_factory, build_session_factory
from app.db.session import warm_up as warm_up_database
from app.services.health import app_version
from app.services.vector_store import build_qdrant_client

logger = logging.getLogger("app")


async def _warm_up(name: str, fn: Callable[[], object]) -> None:
    started = time.perf_counter()
    try:
        await asyncio.to_thread(fn)
        logger.info("%s warmed up in %.2f s", name, time.perf_counter() - started)
    except Exception as exc:  # noqa: BLE001 - the app still starts; /api/health shows the problem
        logger.warning("%s warm-up failed (%s); requests will retry", name, type(exc).__name__)


async def _warm_up_services(app: FastAPI, collection: str) -> None:
    """Open the first Neon connection (~4-5 s) and the first Qdrant HTTPS connection (~0.8 s)
    concurrently, so neither cost lands on a user's first request."""
    await asyncio.gather(
        _warm_up("Database pool", lambda: warm_up_database(app.state.engine)),
        _warm_up("Qdrant connection", lambda: app.state.qdrant.collection_exists(collection)),
    )


def create_app(settings: Settings | None = None, *, warm_up: bool = True) -> FastAPI:
    """Build the app. Tests pass their own settings and `warm_up=False` (no network)."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Startup: create shared clients once; every request reuses them.
        logger.info("Starting (configuration: %s)", settings.describe())
        app.state.engine = build_engine(settings.database_url.get_secret_value())
        app.state.session_factory = build_session_factory(app.state.engine)
        app.state.read_session_factory = build_read_session_factory(app.state.engine)
        app.state.qdrant = build_qdrant_client(settings)
        # Warm-up runs in the background, so the server accepts requests immediately (and
        # `--reload` restarts stay fast). A request that arrives while the warm-up connection is
        # still busy opens a second connection of its own (~1.35 s): measured, not a bug.
        warm_task = (
            asyncio.create_task(_warm_up_services(app, settings.qdrant_collection))
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
    )
    app.state.settings = settings
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(health.router, prefix="/api")
    return app
