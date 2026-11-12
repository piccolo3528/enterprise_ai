"""FastAPI dependencies: how routes get the shared resources created at startup.

Routes ask for what they need (`db: Session = Depends(get_db)`) instead of importing globals,
so tests can hand them substitutes.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from qdrant_client import QdrantClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import NotFoundError, UnauthorizedError
from app.core.security import SESSION_COOKIE, InvalidTokenError, decode_access_token
from app.models import User
from app.services.ingestion.pipeline import SessionFactory
from app.services.storage import Storage
from app.services.vector_store import VectorStore


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


def get_current_user_id(request: Request, settings: SettingsDep) -> uuid.UUID:
    """The signed-in user's id, read from the session cookie. No database query.

    Most routes only need the id (to filter by owner), so this costs no round trip: the token's
    signature proves the id is genuine.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise UnauthorizedError("Please sign in to continue.")
    try:
        return decode_access_token(token, settings.jwt_secret.get_secret_value())
    except InvalidTokenError:
        raise UnauthorizedError("Your session has expired. Please sign in again.") from None


CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]


def get_current_user(user_id: CurrentUserId, db: ReadDbSession) -> User:
    """The full user row, for routes that need more than the id (one read query)."""
    user = db.get(User, user_id)
    if user is None:  # the account was deleted after the token was issued
        raise UnauthorizedError("Your session has expired. Please sign in again.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_kb_id(kb_id: str) -> uuid.UUID:
    """The `{kb_id}` path parameter. A malformed id is "not found" (404), the same answer as
    someone else's id, instead of FastAPI's 422, so every bad id looks alike."""
    try:
        return uuid.UUID(kb_id)
    except ValueError:
        raise NotFoundError("Knowledge base not found.") from None


KbId = Annotated[uuid.UUID, Depends(get_kb_id)]


def get_document_id(document_id: str) -> uuid.UUID:
    """The `{document_id}` path parameter; malformed -> 404, like a missing one."""
    try:
        return uuid.UUID(document_id)
    except ValueError:
        raise NotFoundError("Document not found.") from None


DocumentId = Annotated[uuid.UUID, Depends(get_document_id)]


def get_storage(settings: SettingsDep) -> Storage:
    return Storage(settings.upload_dir)


def get_session_factory(request: Request) -> SessionFactory:
    """For background jobs: they outlive the request, so they open their own sessions."""
    return request.app.state.session_factory


def get_vector_store(request: Request) -> VectorStore:
    return request.app.state.vector_store


StorageDep = Annotated[Storage, Depends(get_storage)]
SessionFactoryDep = Annotated[SessionFactory, Depends(get_session_factory)]
VectorStoreDep = Annotated[VectorStore, Depends(get_vector_store)]
