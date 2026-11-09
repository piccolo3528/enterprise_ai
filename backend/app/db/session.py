"""SQLAlchemy engines + sessions for Neon PostgreSQL (ARCHITECTURE 4.12; decisions D23, D27).

Every setting below comes from a measurement: ~200–290 ms per query round trip and ~1.35 s per
new TLS connection from India to us-east-1 (M1/M2), ~4.5–4.9 s for the very first query, and a
compute that suspends after 5 idle minutes.
"""

from __future__ import annotations

import time
from urllib.parse import urlsplit, urlunsplit

import certifi
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool


def connect_args() -> dict:
    """libpq/psycopg options shared by every engine (app, migrations, tests)."""
    return {
        # A cold start (compute waking up) can take several seconds; 10 s timed out in M1.
        "connect_timeout": 30,
        # Neon's pooler is PgBouncer in transaction mode: no auto-prepared statements.
        "prepare_threshold": None,
        # Start TLS immediately instead of asking "do you speak SSL?" first: one round trip
        # less per new connection (needs libpq >= 17; psycopg bundles 18).
        "sslnegotiation": "direct",
        # Verify Neon's certificate and hostname, not only encrypt. These override the
        # `sslmode=require` in the .env URL, so the URL itself stays portable.
        # certifi's CA bundle is needed on Windows (libpq can't read the Windows store).
        "sslmode": "verify-full",
        "sslrootcert": certifi.where(),
    }


def build_engine(url: str) -> Engine:
    """The app's engine (pooled URL). No connection is opened until the first query."""
    return create_engine(
        url,
        # The pool keeps up to 5 connections open (+5 extra under load) and reuses them, so a
        # request pays per query instead of ~1.35 s to connect first.
        pool_size=5,
        max_overflow=5,
        # Test each pooled connection before use and replace it if Neon's scale-to-zero killed it.
        pool_pre_ping=True,
        # Retire connections after 4 minutes, before the 5-minute idle suspend breaks them.
        pool_recycle=240,
        connect_args=connect_args(),
    )


def build_migration_engine(url: str) -> Engine:
    """Engine for Alembic and test setup: direct URL, no pool (a migration is one short session)."""
    return create_engine(url, poolclass=NullPool, connect_args=connect_args())


def direct_url(pooled_url: str) -> str:
    """Neon's direct endpoint is the pooled host without "-pooler".

    Used to run migrations on the test branch, whose .env entry is the pooled URL.
    """
    parts = urlsplit(pooled_url)
    return urlunsplit(parts._replace(netloc=parts.netloc.replace("-pooler.", ".", 1)))


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Sessions for requests that write: a real transaction (BEGIN ... COMMIT / ROLLBACK)."""
    # expire_on_commit=False: after commit, objects keep their loaded values instead of being
    # re-fetched on next access, which would cost another round trip each time.
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _refuse_writes(session: Session, flush_context, instances) -> None:
    raise RuntimeError(
        "Tried to write through a read-only session; use the DbSession dependency for writes."
    )


def build_read_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Sessions for read-only requests (D27): no BEGIN and no ROLLBACK round trips.

    With autocommit each statement stands alone, so a single SELECT costs one round trip
    instead of three (plus the pre-ping). Reads that must see one consistent snapshot across
    several statements should use a normal session instead. Any attempt to write through a
    read session fails loudly, so a write can't silently happen outside a transaction.
    """
    factory = sessionmaker(
        bind=engine.execution_options(isolation_level="AUTOCOMMIT"),
        autoflush=False,
        expire_on_commit=False,
    )
    event.listen(factory, "before_flush", _refuse_writes)
    return factory


def ping(engine: Engine) -> float:
    """Run `SELECT 1` and return the elapsed seconds (pool checkout + pre-ping + query)."""
    started = time.perf_counter()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return time.perf_counter() - started


def warm_up(engine: Engine) -> float:
    """Open the first pooled connection at startup.

    The first connection pays for the TLS handshake, Neon waking up if it was suspended, and
    SQLAlchemy's one-time dialect setup queries (~4.5–4.9 s). Doing it at startup means no user
    request waits for it. It's a single call at startup, not a keep-alive: pinging every few
    minutes would stop Neon from ever suspending and use up the free plan's compute hours.
    """
    return ping(engine)
