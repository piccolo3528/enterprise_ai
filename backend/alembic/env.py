"""Alembic environment: how migrations connect and what they compare against.

Migrations always use Neon's DIRECT endpoint (decision D18): PgBouncer's transaction pooling
doesn't keep the session state migration tools rely on.

Targets (choose with -x target=...):
  dev  (default)  DATABASE_MIGRATION_URL
  test            TEST_DATABASE_URL, switched to its direct endpoint
Tests can also pass a URL directly via config.attributes["url"].
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import ConfigError, load_settings
from app.db.base import Base
from app.db.session import build_migration_engine, direct_url

config = context.config
if config.config_file_name and not config.attributes.get("skip_logging_config"):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    explicit = config.attributes.get("url")
    if explicit:
        return explicit

    target = context.get_x_argument(as_dictionary=True).get("target", "dev")
    settings = load_settings()
    if target == "dev":
        url = settings.database_migration_url
        if url is None:
            raise ConfigError("DATABASE_MIGRATION_URL is not set in backend/.env")
        return url.get_secret_value()
    if target == "test":
        url = settings.test_database_url
        if url is None:
            raise ConfigError("TEST_DATABASE_URL is not set in backend/.env")
        return direct_url(url.get_secret_value())
    raise ConfigError(f"Unknown migration target {target!r}; use 'dev' or 'test'")


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL instead of running it (for review)."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = build_migration_engine(database_url())
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,  # also detect changed column types, not only new columns
            )
            # PostgreSQL DDL is transactional: if any step fails, the whole migration rolls back.
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
