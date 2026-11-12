"""Plain helpers shared by tests (fixtures live in the conftest.py files)."""

from __future__ import annotations

import uuid

from alembic.config import Config

from app.core.config import BACKEND_DIR, Settings, load_settings
from app.core.security import SESSION_COOKIE, create_access_token
from app.models import User

# Fake but well-formed values. Port 5999/6999: nothing listens there, so an accidental real
# connection fails fast instead of reaching a real service.
FAKE_DB_PASSWORD = "fake-db-password-123"
FAKE_JWT_SECRET = "unit-test-jwt-secret-that-is-long-enough-0123456789"
BASE_VALUES = {
    "database_url": f"postgresql+psycopg://tester:{FAKE_DB_PASSWORD}@127.0.0.1:5999/testdb",
    "jwt_secret": FAKE_JWT_SECRET,
    "qdrant_url": "http://127.0.0.1:6999",
    "gemini_api_key": "fake-gemini-key",
}


def make_settings(**overrides) -> Settings:
    """Settings for unit tests, built from fake values only (backend/.env is ignored)."""
    values = {**BASE_VALUES, **overrides}
    return load_settings(_env_file=None, **values)


# Live tests use this Qdrant collection, never the app's own (tests/integration/conftest.py).
TEST_COLLECTION = "chunks_test"


def live_settings(**overrides) -> Settings:
    """backend/.env settings (real services) aimed at the test collection."""
    return load_settings(qdrant_collection=TEST_COLLECTION, **overrides)


def alembic_config(url: str) -> Config:
    """Alembic config aimed at an explicit database URL (the Neon test branch in tests)."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["url"] = url
    config.attributes["skip_logging_config"] = True  # keep pytest's own logging setup
    return config


# --- database tests (Neon test branch) --------------------------------------------------------


def save(db, *rows):
    """Add rows and commit. In these tests a commit only releases a SAVEPOINT (the outer
    transaction is still rolled back at the end), but it means a request that rolls back its own
    work can't undo the test's setup with it."""
    db.add_all(rows)
    db.commit()
    return rows[0]


def make_user(db, name="Test User") -> User:
    email = f"u-{uuid.uuid4().hex[:10]}@example.com"
    return save(db, User(email=email, password_hash="x", full_name=name))


def act_as(client, user) -> None:
    """Switch a TestClient's session cookie to this user (`client.secret` = the JWT secret)."""
    client.cookies.clear()
    token = create_access_token(user.id, client.secret, expires_minutes=5)
    # No domain: Python's cookiejar treats the dotless host "testserver" as "testserver.local",
    # so a cookie scoped to domain="testserver" would silently never be sent.
    client.cookies.set(SESSION_COOKIE, token)
