"""Shared fixtures. Unit tests never read backend/.env and never touch the network."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.factory import create_app
from tests.helpers import make_settings


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
