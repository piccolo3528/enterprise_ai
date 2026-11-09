"""Plain helpers shared by tests (fixtures live in the conftest.py files)."""

from __future__ import annotations

from alembic.config import Config

from app.core.config import BACKEND_DIR, Settings, load_settings

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


def alembic_config(url: str) -> Config:
    """Alembic config aimed at an explicit database URL (the Neon test branch in tests)."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["url"] = url
    config.attributes["skip_logging_config"] = True  # keep pytest's own logging setup
    return config
