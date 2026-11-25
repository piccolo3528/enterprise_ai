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
from app.core.errors import LLMNotConfiguredError, NotFoundError, UnauthorizedError
from app.core.rate_limit import RateLimits
from app.core.security import SESSION_COOKIE, InvalidTokenError, decode_session
from app.core.sessions import TokenVersions
from app.models import User
from app.services.ingestion.pipeline import SessionFactory
from app.services.llm import LLMProvider
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


SESSION_ENDED = "You were signed out because your password changed. Please sign in again."


def get_token_versions(request: Request) -> TokenVersions:
    return request.app.state.token_versions


def get_current_user_id(request: Request, settings: SettingsDep, db: ReadDbSession) -> uuid.UUID:
    """The signed-in user's id, read from the session cookie.

    Most routes only need the id (to filter by owner): the token's signature proves the id is
    genuine. Its version must still be the user's current one (M16, core/sessions.py): that is
    read from the database once per user per server start, then kept in memory, so a normal
    request still costs no extra round trip. The session `db` only connects on that first read
    (FastAPI hands the same session to a route that also asks for ReadDbSession).
    """
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise UnauthorizedError("Please sign in to continue.")
    try:
        user_id, version = decode_session(token, settings.jwt_secret.get_secret_value())
    except InvalidTokenError:
        raise UnauthorizedError("Your session has expired. Please sign in again.") from None
    current = get_token_versions(request).current(db, user_id)
    if current is None:  # the account was deleted after the token was issued
        raise UnauthorizedError("Your session has expired. Please sign in again.")
    if version != current:
        raise UnauthorizedError(SESSION_ENDED)
    return user_id


CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]


def get_optional_user_id(
    request: Request, settings: SettingsDep, db: ReadDbSession
) -> uuid.UUID | None:
    """The signed-in user's id, or None (no error) for routes that serve everyone but show
    more to signed-in users (the health check)."""
    if not request.cookies.get(SESSION_COOKIE):
        return None
    try:
        return get_current_user_id(request, settings, db)
    except UnauthorizedError:
        return None


OptionalUserId = Annotated[uuid.UUID | None, Depends(get_optional_user_id)]


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


def get_conversation_id(conversation_id: str) -> uuid.UUID:
    """The `{conversation_id}` path parameter; malformed -> 404, like a missing one."""
    try:
        return uuid.UUID(conversation_id)
    except ValueError:
        raise NotFoundError("Conversation not found.") from None


ConversationId = Annotated[uuid.UUID, Depends(get_conversation_id)]


def get_storage(settings: SettingsDep) -> Storage:
    return Storage(settings.upload_dir)


def get_session_factory(request: Request) -> SessionFactory:
    """For background jobs: they outlive the request, so they open their own sessions."""
    return request.app.state.session_factory


def get_read_session_factory(request: Request) -> SessionFactory:
    """Autocommit sessions (D27) for work that outlives the request's own dependencies, such as
    the retrieval step of a streamed answer."""
    return request.app.state.read_session_factory


def get_vector_store(request: Request) -> VectorStore:
    return request.app.state.vector_store


def get_llm(request: Request) -> LLMProvider:
    """The answer model (with its fallback chain) built at startup; None means no LLM key."""
    llm = request.app.state.llm
    if llm is None:
        raise LLMNotConfiguredError(
            "AI answers aren't set up on this server: set GEMINI_API_KEY (or GROQ_API_KEY) in "
            "backend/.env."
        )
    return llm


def get_limits(request: Request) -> RateLimits:
    """The per-user request limits (M16), shared by every request of this process."""
    return request.app.state.limits


def get_client_address(request: Request) -> str:
    """The caller's address, for per-address limits. Behind the Vite proxy (or any proxy on
    127.0.0.1) uvicorn takes it from X-Forwarded-For, which only trusted proxy addresses may set
    (uvicorn's --forwarded-allow-ips, default 127.0.0.1); otherwise it is the socket's peer."""
    return request.client.host if request.client else "unknown"


StorageDep = Annotated[Storage, Depends(get_storage)]
LimitsDep = Annotated[RateLimits, Depends(get_limits)]
TokenVersionsDep = Annotated[TokenVersions, Depends(get_token_versions)]
ClientAddress = Annotated[str, Depends(get_client_address)]
LLMDep = Annotated[LLMProvider, Depends(get_llm)]
SessionFactoryDep = Annotated[SessionFactory, Depends(get_session_factory)]
ReadSessionFactoryDep = Annotated[SessionFactory, Depends(get_read_session_factory)]
VectorStoreDep = Annotated[VectorStore, Depends(get_vector_store)]
