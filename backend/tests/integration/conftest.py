"""Database fixtures for integration tests. They run ONLY on the Neon "test" branch.

Each test runs inside a transaction that is rolled back afterwards, so tests never see each
other's rows and the branch stays empty.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest
from alembic import command
from sqlalchemy.orm import Session

from app.core.config import load_settings
from app.db.session import build_engine, direct_url
from tests.helpers import alembic_config, make_user


@pytest.fixture(scope="session")
def test_database_url() -> str:
    settings = load_settings()
    if settings.test_database_url is None:
        pytest.skip("TEST_DATABASE_URL is not set: create the Neon 'test' branch first")
    test_url = settings.test_database_url.get_secret_value()
    dev_host = urlsplit(settings.database_url.get_secret_value()).hostname
    if urlsplit(test_url).hostname == dev_host:
        pytest.fail("TEST_DATABASE_URL points at the development database; refusing to run")
    # Direct endpoint: tests use savepoints and DDL, which belong on a real session.
    return direct_url(test_url)


@pytest.fixture(scope="session")
def test_engine(test_database_url):
    """Engine on the test branch, with the schema migrated to the latest version."""
    command.upgrade(alembic_config(test_database_url), "head")
    engine = build_engine(test_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(test_engine) -> Session:
    """A session whose work is always rolled back, even if the test commits."""
    with test_engine.connect() as connection:
        outer = connection.begin()
        # session.commit() inside a test releases a SAVEPOINT instead of committing for real.
        session = Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            session.close()
            outer.rollback()


@pytest.fixture
def alice(db):
    return make_user(db, "Alice")


@pytest.fixture
def bob(db):
    return make_user(db, "Bob")
