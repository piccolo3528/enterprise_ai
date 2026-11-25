"""Unit-test fixtures. Unit tests never touch the network."""

from __future__ import annotations

import pytest

from app.core import sessions


@pytest.fixture(autouse=True)
def token_versions_without_a_database(monkeypatch):
    """Every user's token version is 0, as for tokens made by `create_access_token` without a
    version. The real lookup reads PostgreSQL; tests of the version check set their own."""
    versions = {}

    def load(db, user_id):
        return versions.get(user_id, 0)

    monkeypatch.setattr(sessions, "load_token_version", load)
    return versions
