"""Search end to end: real PostgreSQL full-text search (Neon test branch, rolled back), the real
embedding model and real Qdrant (the "chunks_test" collection).

Each document below is one short paragraph, so it becomes exactly one chunk, and every query has
one right answer.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.api.deps import get_db, get_read_db, get_session_factory, get_vector_store
from app.factory import create_app
from app.models import Document
from app.services.retrieval import HYBRID_DEGRADED, ONLY_COMMON_WORDS, RRF_K
from tests.helpers import act_as, live_settings
from tests.integration.test_documents_api import documents, new_kb, unreachable_store, upload

pytestmark = pytest.mark.live

MODES = ("semantic", "keyword", "hybrid")

DOCS = {
    "leave.txt": "Unused annual leave can be carried forward into the next year, up to ten days.",
    "remote.txt": "Employees may work from another country for up to thirty days a year.",
    "expenses.txt": "Travel expenses are reimbursed within fourteen days of submitting receipts.",
    "codes.txt": "Policy NX-HR-002 is owned by the People team and reviewed every year.",
}


@pytest.fixture
def client(db, tmp_path, vector_store):
    settings = live_settings(upload_dir=tmp_path / "uploads")
    app = create_app(settings, warm_up=False)
    app.dependency_overrides[get_vector_store] = lambda: vector_store
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_read_db] = lambda: db

    @contextmanager
    def shared_session():
        yield db

    app.dependency_overrides[get_session_factory] = lambda: shared_session
    with TestClient(app, base_url="https://testserver") as c:
        c.secret = settings.jwt_secret.get_secret_value()
        c.vectors = vector_store
        yield c


def library(client, user) -> tuple[str, dict[str, str]]:
    """A knowledge base holding DOCS for `user`: (kb_id, filename -> document id)."""
    act_as(client, user)
    kb_id = new_kb(client)
    for name, text in DOCS.items():
        assert upload(client, kb_id, name, text.encode()).status_code == 202
    docs = {d["original_filename"]: d["id"] for d in documents(client, kb_id)}
    assert len(docs) == len(DOCS)
    return kb_id, docs


def search(client, kb_id, query, **options):
    return client.post(f"/api/knowledge-bases/{kb_id}/search", json={"query": query, **options})


def found(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [r["filename"] for r in response.json()["results"]]


@pytest.mark.parametrize("mode", MODES)
def test_every_mode_finds_the_carry_forward_passage_first(client, alice, mode):
    kb_id, docs = library(client, alice)
    response = search(client, kb_id, "carry forward leave", mode=mode)
    body = response.json()
    assert found(response)[0] == "leave.txt"
    assert body["mode"] == mode
    top = body["results"][0]
    assert top["document_id"] == docs["leave.txt"]
    assert top["text"] == DOCS["leave.txt"]
    assert (top["chunk_index"], top["page_start"], top["doc_code"]) == (0, None, None)
    if mode == "semantic":
        assert 0 < top["score"] <= 1 and top["score"] == top["semantic_score"]
    if mode == "keyword":
        # "carry", "forward", "leave": all three words, plus a rank below 1.
        assert top["keyword_matched"] == 3 and 3 < top["score"] < 4
    if mode == "hybrid":
        expected = 1 / (RRF_K + top["semantic_rank"]) + 1 / (RRF_K + top["keyword_rank"])
        assert top["score"] == pytest.approx(expected)
    assert {"connect_and_scope_check", "load_passages", "total"} <= set(body["timings_ms"])


def test_keyword_needs_shared_words_semantic_does_not(client, alice):
    kb_id, _ = library(client, alice)
    # No document contains "overseas" or "abroad"...
    keyword = search(client, kb_id, "working overseas abroad", mode="keyword")
    assert found(keyword) == ["remote.txt"]  # ...only "work" matches, by its stem
    assert search(client, kb_id, "overseas abroad", mode="keyword").json()["results"] == []
    # ...but meaning does: the remote-work passage is the nearest vector.
    semantic = found(search(client, kb_id, "overseas abroad", mode="semantic"))
    assert semantic[0] == "remote.txt" and len(semantic) == len(DOCS)


def test_an_exact_code_is_found_by_keyword_and_hybrid(client, alice):
    kb_id, _ = library(client, alice)
    assert found(search(client, kb_id, "NX-HR-002", mode="keyword")) == ["codes.txt"]
    assert found(search(client, kb_id, "NX-HR-002", mode="hybrid"))[0] == "codes.txt"


def test_semantic_scores_are_sorted_and_the_threshold_cuts_them(client, alice):
    kb_id, _ = library(client, alice)
    results = search(client, kb_id, "reimbursing travel costs", mode="semantic").json()["results"]
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True) and results[0]["filename"] == "expenses.txt"
    cut = (scores[0] + scores[1]) / 2  # between the 1st and the 2nd
    limited = search(client, kb_id, "reimbursing travel costs", mode="semantic", min_score=cut)
    assert found(limited) == ["expenses.txt"]
    assert found(search(client, kb_id, "travel", mode="semantic", min_score=0.99)) == []


def test_top_k_limits_the_results(client, alice):
    kb_id, _ = library(client, alice)
    for mode in ("semantic", "hybrid"):
        assert len(found(search(client, kb_id, "policy", mode=mode, top_k=2))) == 2


def test_the_document_filter_keeps_one_document(client, alice):
    kb_id, docs = library(client, alice)
    for mode in MODES:
        response = search(client, kb_id, "days", mode=mode, document_id=docs["remote.txt"])
        assert found(response) == ["remote.txt"]


def test_a_document_outside_the_knowledge_base_is_not_found(client, alice, bob):
    kb_id, _ = library(client, alice)
    _, other_docs = library(client, alice)  # alice's own, but in another knowledge base
    _, bobs_docs = library(client, bob)
    act_as(client, alice)
    for document_id in (other_docs["leave.txt"], bobs_docs["leave.txt"], str(uuid.uuid4())):
        response = search(client, kb_id, "leave", document_id=document_id)
        assert response.status_code == 404
        assert response.json()["error"]["message"] == "Document not found."


def test_search_never_crosses_users_or_knowledge_bases(client, alice, bob):
    alice_kb, alice_docs = library(client, alice)
    bob_kb, bob_docs = library(client, bob)  # the very same texts, in Bob's knowledge base
    act_as(client, alice)
    for mode in MODES:
        response = search(client, alice_kb, "carry forward leave", mode=mode, top_k=50)
        returned = {r["document_id"] for r in response.json()["results"]}
        assert returned and returned <= set(alice_docs.values())
        assert not returned & set(bob_docs.values())
    # Bob's knowledge base and a made-up one look exactly alike to Alice.
    theirs = search(client, bob_kb, "leave")
    missing = search(client, str(uuid.uuid4()), "leave")
    assert theirs.status_code == missing.status_code == 404
    assert theirs.json()["error"]["message"] == missing.json()["error"]["message"]


def test_only_ready_documents_are_searchable(client, db, alice):
    kb_id, docs = library(client, alice)
    # Being reprocessed: its chunks and points still exist, but it isn't "ready".
    db.execute(update(Document).where(Document.id == docs["leave.txt"]).values(status="processing"))
    db.commit()
    for mode in MODES:
        assert "leave.txt" not in found(search(client, kb_id, "carry forward leave", mode=mode))


def test_a_query_of_only_common_words(client, alice):
    kb_id, _ = library(client, alice)
    body = search(client, kb_id, "what is the", mode="keyword").json()
    assert (body["results"], body["query_terms"], body["notice"]) == ([], 0, ONLY_COMMON_WORDS)


@pytest.mark.parametrize(
    "query",
    ["O'Brien's \"leave\"", "a\\b \\\\ ''", "leave'); DROP TABLE chunks; --", "-leave OR !(x) <->"],
)
def test_quotes_backslashes_and_operators_are_just_text(client, alice, query):
    kb_id, _ = library(client, alice)
    for mode in ("keyword", "hybrid"):
        assert search(client, kb_id, query, mode=mode).status_code == 200


def test_an_empty_knowledge_base_returns_no_results(client, alice):
    act_as(client, alice)
    kb_id = new_kb(client)
    for mode in MODES:
        assert found(search(client, kb_id, "leave", mode=mode)) == []


def test_when_qdrant_is_down_semantic_fails_and_hybrid_degrades(client, alice):
    kb_id, _ = library(client, alice)
    client.app.dependency_overrides[get_vector_store] = unreachable_store
    semantic = search(client, kb_id, "carry forward leave", mode="semantic")
    assert semantic.status_code == 503
    assert "Keyword search still works" in semantic.json()["error"]["message"]

    hybrid = search(client, kb_id, "carry forward leave", mode="hybrid").json()
    assert hybrid["notice"] == HYBRID_DEGRADED
    assert hybrid["results"][0]["filename"] == "leave.txt"
    assert hybrid["results"][0]["semantic_rank"] is None

    keyword = search(client, kb_id, "carry forward leave", mode="keyword").json()
    assert keyword["notice"] is None and keyword["results"][0]["filename"] == "leave.txt"
