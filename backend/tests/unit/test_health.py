"""GET /api/health with the database and Qdrant replaced by fakes."""

from __future__ import annotations

import re
import time

import pytest
from fastapi.testclient import TestClient

from app.factory import create_app
from app.services import health as health_service
from tests.helpers import make_settings


class FakeQdrant:
    def __init__(self, exists=False, delay=0.0, error=None):
        self.exists, self.delay, self.error = exists, delay, error

    def collection_exists(self, name):
        time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.exists

    def close(self):
        pass


@pytest.fixture
def fake_db(monkeypatch):
    """Replace the database ping; set `.delay` / `.error` per test."""

    class FakeDb:
        delay = 0.0
        error = None

        def ping(self, engine):
            time.sleep(self.delay)
            if self.error:
                raise self.error
            return self.delay

    fake = FakeDb()
    monkeypatch.setattr(health_service.db_session, "ping", fake.ping)
    return fake


def get_health(client, qdrant=None):
    client.app.state.qdrant = qdrant or FakeQdrant()
    return client.get("/api/health")


def test_all_services_ok(client, fake_db):
    response = get_health(client, FakeQdrant(exists=True))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["services"]["database"]["status"] == "ok"
    assert body["services"]["vector_store"] == {
        "status": "ok",
        "latency_ms": body["services"]["vector_store"]["latency_ms"],
        "detail": None,
        "collection": "chunks",
        "collection_exists": True,
    }
    llm = body["services"]["llm"]
    assert llm["api_key_configured"] is True
    assert llm["answer_model"] == "gemini-3.5-flash-lite"
    assert body["models"]["embedding"] == "BAAI/bge-small-en-v1.5"


def test_response_carries_a_request_id(client, fake_db):
    response = get_health(client)
    assert re.fullmatch(r"[0-9a-f]{12}", response.headers["X-Request-ID"])


def test_database_failure_is_reported_without_leaking_details(client, fake_db):
    fake_db.error = RuntimeError("connection to ep-secret-host.neon.tech failed for user bob")
    response = get_health(client)
    assert response.status_code == 200  # the report itself still works
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"]["database"]["status"] == "error"
    assert body["services"]["database"]["detail"] == "RuntimeError"
    assert "ep-secret-host" not in response.text
    assert body["services"]["vector_store"]["status"] == "ok"  # one failure doesn't hide the rest


def test_vector_store_failure_is_reported(client, fake_db):
    response = get_health(client, FakeQdrant(error=ConnectionError("refused")))
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"]["vector_store"]["status"] == "error"
    assert body["services"]["vector_store"]["collection_exists"] is None


def test_slow_service_times_out(client, fake_db, monkeypatch):
    monkeypatch.setattr(health_service, "CHECK_TIMEOUT_S", 0.2)
    fake_db.delay = 1.0
    started = time.perf_counter()
    body = get_health(client).json()
    assert time.perf_counter() - started < 0.9  # didn't wait for the slow call
    assert body["services"]["database"]["status"] == "error"
    assert body["services"]["database"]["detail"].startswith("no response within")


def test_checks_run_concurrently(client, fake_db):
    fake_db.delay = 0.4
    started = time.perf_counter()
    body = get_health(client, FakeQdrant(delay=0.4)).json()
    elapsed = time.perf_counter() - started
    assert body["status"] == "ok"
    assert elapsed < 0.75, f"took {elapsed:.2f} s; sequential would be >= 0.8 s"


def test_missing_gemini_key_marks_degraded(fake_db):
    settings = make_settings(gemini_api_key=None)
    with TestClient(create_app(settings, warm_up=False)) as client:
        body = get_health(client).json()
    assert body["status"] == "degraded"
    assert body["services"]["llm"]["api_key_configured"] is False
