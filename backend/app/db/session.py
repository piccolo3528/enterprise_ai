"""SQLAlchemy engine + sessions for Neon PostgreSQL (ARCHITECTURE section 4.12, decision D23).

Every setting below comes from an M1 measurement (laptop in India -> Neon us-east-1):
~290 ms per query round trip, ~1.35 s per new TLS connection, ~4.9 s for the very first query,
and a compute that suspends after 5 idle minutes.
"""

from __future__ import annotations

import time

import certifi
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker


def build_engine(url: str) -> Engine:
    """Create the engine. No connection is opened until the first query."""
    return create_engine(
        url,
        # The pool keeps up to 5 connections open (+5 extra under load) and reuses them, so a
        # request pays ~290 ms per query instead of ~1.35 s to connect first.
        pool_size=5,
        max_overflow=5,
        # Test each pooled connection before use and replace it if Neon's scale-to-zero killed it.
        pool_pre_ping=True,
        # Retire connections after 4 minutes, before the 5-minute idle suspend breaks them.
        pool_recycle=240,
        connect_args={
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
        },
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False: after commit, objects keep their loaded values instead of being
    # re-fetched on next access, which would cost another ~290 ms round trip each time.
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def ping(engine: Engine) -> float:
    """Run `SELECT 1` and return the elapsed seconds (pool checkout + pre-ping + query)."""
    started = time.perf_counter()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return time.perf_counter() - started


def warm_up(engine: Engine) -> float:
    """Open the first pooled connection at startup.

    The first connection pays for the TLS handshake, Neon waking up if it was suspended, and
    SQLAlchemy's one-time dialect setup queries (~4.9 s in M1). Doing it at startup means no user
    request waits for it. It's a single call at startup, not a keep-alive: pinging every few
    minutes would stop Neon from ever suspending and use up the free plan's compute hours.
    """
    return ping(engine)
