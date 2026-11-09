"""FastAPI dependencies: how routes get the shared resources created at startup.

Routes ask for what they need (`db: Session = Depends(get_db)`) instead of importing globals,
so tests can hand them substitutes.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from qdrant_client import QdrantClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


def get_qdrant(request: Request) -> QdrantClient:
    return request.app.state.qdrant


def get_db(request: Request) -> Iterator[Session]:
    """A transactional session for requests that write. Always closed, returning its connection
    to the pool; uncommitted work is rolled back."""
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_read_db(request: Request) -> Iterator[Session]:
    """An autocommit session for read-only requests: fewer round trips per query (D27)."""
    session = request.app.state.read_session_factory()
    try:
        yield session
    finally:
        session.close()


# Type aliases for route signatures: `def route(db: DbSession): ...`
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
EngineDep = Annotated[Engine, Depends(get_engine)]
QdrantDep = Annotated[QdrantClient, Depends(get_qdrant)]
DbSession = Annotated[Session, Depends(get_db)]
ReadDbSession = Annotated[Session, Depends(get_read_db)]
