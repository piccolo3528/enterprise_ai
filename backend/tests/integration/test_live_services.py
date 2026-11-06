"""Live checks against the real Neon + Qdrant in backend/.env. Run with: pytest -m live"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import load_settings
from app.factory import create_app

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_client():
    with TestClient(create_app(load_settings(), warm_up=False)) as client:
        yield client


def test_health_reports_real_services_ok(live_client):
    body = live_client.get("/api/health").json()
    assert body["services"]["database"]["status"] == "ok", body
    assert body["services"]["vector_store"]["status"] == "ok", body
    assert body["services"]["llm"]["api_key_configured"] is True
    assert body["status"] == "ok"


def test_database_connection_verifies_the_certificate(live_client):
    """The engine's connect_args must override the URL's `sslmode=require`."""
    engine = live_client.app.state.engine
    with engine.connect() as conn:
        pg = conn.connection.driver_connection
        params = pg.info.get_parameters()
        assert pg.pgconn.ssl_in_use
        assert params.get("sslmode") == "verify-full"
        assert params.get("sslnegotiation") == "direct"
        assert params.get("sslrootcert", "").endswith("cacert.pem")  # certifi's bundle


def test_session_factory_runs_queries(live_client):
    with live_client.app.state.session_factory() as session:
        assert session.execute(text("SELECT 1")).scalar() == 1
