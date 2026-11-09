"""Migrations work in both directions and match the models. Runs on the Neon test branch."""

from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import inspect

from app.db.base import Base
from app.db.session import build_migration_engine
from tests.helpers import alembic_config

pytestmark = pytest.mark.live


def table_names(url: str) -> set[str]:
    engine = build_migration_engine(url)
    try:
        return set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()


def test_downgrade_then_upgrade_round_trip(test_engine, test_database_url):
    config = alembic_config(test_database_url)
    expected = set(Base.metadata.tables)

    command.downgrade(config, "base")
    assert table_names(test_database_url) == set()

    command.upgrade(config, "head")
    assert table_names(test_database_url) == expected


def test_models_and_migrations_are_in_sync(test_engine, test_database_url):
    # Fails if a model was changed without generating a migration for it.
    command.check(alembic_config(test_database_url))
