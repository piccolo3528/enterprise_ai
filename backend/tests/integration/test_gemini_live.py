"""Smoke tests against the **real Gemini API**: 6 calls per run, so they are opt-in.

    pytest -m gemini          # needs GEMINI_API_KEY; skipped without it

Everything else is as in test_answer_api.py (Neon test branch rolled back, "chunks_test").
LLM output varies, so the checks are deliberately loose: the right fact, a valid citation, the
not-found reply, and an injected instruction that doesn't take over.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_db,
    get_read_db,
    get_read_session_factory,
    get_session_factory,
    get_vector_store,
)
from app.factory import create_app
from app.services import rag
from tests.helpers import live_settings
from tests.integration.test_answer_api import EXPENSES, INJECTED, LEAVE, ask, library
from tests.integration.test_conversations_api import KeepOpen, follow_up, start

pytestmark = pytest.mark.gemini


@pytest.fixture
def client(db, tmp_path, vector_store):
    settings = live_settings(upload_dir=tmp_path / "uploads")
    if settings.gemini_api_key is None:
        pytest.skip("GEMINI_API_KEY is not set")
    app = create_app(settings, warm_up=False)  # the real LLM, built by the lifespan
    app.dependency_overrides[get_vector_store] = lambda: vector_store
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_read_db] = lambda: KeepOpen(db)

    @contextmanager
    def shared_session():
        yield db

    app.dependency_overrides[get_session_factory] = lambda: shared_session
    app.dependency_overrides[get_read_session_factory] = lambda: shared_session
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


def test_a_streamed_follow_up_is_rewritten_and_answered(client, alice):
    """M13: 3 calls (first answer, rewrite in JSON mode, follow-up answer)."""
    kb_id = library(client, alice, {"leave.txt": LEAVE, "expenses.txt": EXPENSES})
    first = start(client, kb_id, "What does the policy say about unused annual leave?")
    assert [name for name, _ in first][-1] == "done", first
    tokens = "".join(data["text"] for name, data in first if name == "token")
    assert tokens == first[-1][1]["answer"] and first[-1][1]["not_found"] is False

    events = follow_up(client, first[0][1]["id"], "How many days of it can I keep?")
    done = events[-1][1]
    assert events[-1][0] == "done", events
    assert "leave" in (done["rewritten_query"] or "").lower(), done["rewritten_query"]
    assert "ten" in done["answer"].lower() or "10" in done["answer"], done["answer"]
    assert any(c["filename"] == "leave.txt" for c in events[-2][1])
