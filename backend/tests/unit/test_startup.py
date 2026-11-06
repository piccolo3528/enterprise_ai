"""Startup warm-up: runs in the background and never stops the app from starting."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app import factory


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_warm_up_runs_and_a_failure_does_not_block_startup(settings, monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(factory, "warm_up_database", lambda engine: calls.append("db"))
    caplog.set_level("INFO")

    # Qdrant points at 127.0.0.1:6999 where nothing listens, so its warm-up fails.
    with TestClient(factory.create_app(settings, warm_up=True)) as client:
        assert wait_for(lambda: "Qdrant connection warm-up failed" in caplog.text)
        assert wait_for(lambda: "Database pool warmed up" in caplog.text)
        assert calls == ["db"]
        # The app still serves requests.
        assert client.get("/api/does-not-exist").status_code == 404
