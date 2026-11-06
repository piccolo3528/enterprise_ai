"""Shared fixtures. Unit tests never read backend/.env and never touch the network."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, load_settings
from app.factory import create_app

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
    values = {**BASE_VALUES, **overrides}
    return load_settings(_env_file=None, **values)  # _env_file=None: ignore backend/.env


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings):
    return create_app(settings, warm_up=False)


@pytest.fixture
def client(app):
    with TestClient(app) as c:  # `with` runs the lifespan (startup/shutdown)
        yield c
