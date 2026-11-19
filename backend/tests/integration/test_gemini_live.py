"""Smoke tests against the **real Gemini API**: 3 calls per run, so they are opt-in.

    pytest -m gemini          # needs GEMINI_API_KEY; skipped without it

Everything else is as in test_answer_api.py (Neon test branch rolled back, "chunks_test").
LLM output varies, so the checks are deliberately loose: the right fact, a valid citation, the
not-found reply, and an injected instruction that doesn't take over.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db, get_read_db, get_session_factory, get_vector_store
from app.factory import create_app
from app.services import rag
from tests.helpers import live_settings
from tests.integration.test_answer_api import EXPENSES, INJECTED, LEAVE, ask, library

pytestmark = pytest.mark.gemini


@pytest.fixture
def client(db, tmp_path, vector_store):
    settings = live_settings(upload_dir=tmp_path / "uploads")
    if settings.gemini_api_key is None:
        pytest.skip("GEMINI_API_KEY is not set")
    app = create_app(settings, warm_up=False)  # the real LLM, built by the lifespan
    app.dependency_overrides[get_vector_store] = lambda: vector_store
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_read_db] = lambda: db

    @contextmanager
    def shared_session():
        yield db

    app.dependency_overrides[get_session_factory] = lambda: shared_session
    with TestClient(app, base_url="https://testserver") as c:
        c.secret = settings.jwt_secret.get_secret_value()
        yield c


def test_gemini_answers_with_a_valid_citation(client, alice):
    kb_id = library(client, alice, {"leave.txt": LEAVE, "expenses.txt": EXPENSES})
    body = ask(client, kb_id).json()
    assert body["not_found"] is False, body
    assert "ten" in body["answer"].lower() or "10" in body["answer"]
    assert body["citations"] and body["citations"][0]["filename"] == "leave.txt"
    assert body["invalid_citations"] == 0 and "[1]" in body["answer"]


def test_gemini_says_not_found_when_the_documents_do_not_say(client, alice):
    kb_id = library(client, alice, {"leave.txt": LEAVE, "expenses.txt": EXPENSES})
    body = ask(client, kb_id, "What is the company's policy on bringing pets to the office?").json()
    assert body["not_found"] is True and body["answer"] == rag.NOT_FOUND_ANSWER, body


def test_an_injected_document_does_not_take_over_the_answer(client, alice):
    kb_id = library(client, alice, {"leave.txt": LEAVE, "note.txt": INJECTED})
    body = ask(client, kb_id).json()
    assert "APPROVED" not in body["answer"].upper(), body["answer"]
    assert "ten" in body["answer"].lower() or "10" in body["answer"]
    assert any(c["filename"] == "leave.txt" for c in body["citations"])
