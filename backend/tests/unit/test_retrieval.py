"""Retrieval without services: RRF on hand-made rankings, the search orchestration with fakes in
place of PostgreSQL and Qdrant, the request rules, and the route guards."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.core.errors import NotFoundError, ServiceUnavailableError
from app.core.security import SESSION_COOKIE, create_access_token
from app.schemas.search import QUERY_MAX, SearchRequest
from app.services import retrieval
from app.services.keyword_search import KeywordHit
from app.services.retrieval import (
    HYBRID_DEGRADED,
    ONLY_COMMON_WORDS,
    Passage,
    reciprocal_rank_fusion,
)
from app.services.vector_store import SearchHit
from tests.helpers import FAKE_JWT_SECRET

# --- Reciprocal Rank Fusion, checked against values worked out by hand -------------------------


def test_rrf_matches_hand_computed_scores():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "a", "d"]], k=60)
    expected = {
        "a": 1 / 61 + 1 / 62,  # 1st and 2nd   = 0.032523
        "c": 1 / 63 + 1 / 61,  # 3rd and 1st   = 0.032266
        "b": 1 / 62,  # 2nd in one list only    = 0.016129
        "d": 1 / 63,  # 3rd in one list only    = 0.015873
    }
    assert [item for item, _ in fused] == ["a", "c", "b", "d"]
    for item, score in fused:
        assert score == pytest.approx(expected[item], abs=1e-12)


def test_agreement_beats_a_single_first_place():
    # y is only 2nd in each list, x is 1st in one list: being found by both wins.
    fused = dict(reciprocal_rank_fusion([["x", "y"], ["z", "y"]]))
    assert fused["y"] == pytest.approx(2 / 62)
    assert fused["x"] == pytest.approx(1 / 61)
    assert fused["y"] > fused["x"]


def test_rrf_ignores_raw_scores_and_uses_k():
    # k = 0 gives plain 1/rank; with a large k, ranks barely matter.
    assert dict(reciprocal_rank_fusion([["a", "b"]], k=0)) == {"a": 1.0, "b": 0.5}
    big = dict(reciprocal_rank_fusion([["a", "b"]], k=10_000))
    assert big["a"] / big["b"] == pytest.approx(10_002 / 10_001)


def test_rrf_ties_keep_first_seen_order_and_repeats_count_once():
    assert [i for i, _ in reciprocal_rank_fusion([["a"], ["b"]])] == ["a", "b"]
    assert [i for i, _ in reciprocal_rank_fusion([["b"], ["a"]])] == ["b", "a"]
    assert dict(reciprocal_rank_fusion([["a", "a", "b"]])) == {"a": 1 / 61, "b": 1 / 63}
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


# --- search(): the orchestration, with PostgreSQL and Qdrant replaced by fakes ---------------

OWNER, KB = uuid.uuid4(), uuid.uuid4()
IDS = [uuid.UUID(int=i) for i in range(1, 8)]  # c1..c7


def passage(chunk_id: uuid.UUID) -> Passage:
    return Passage(
        chunk_id=chunk_id,
        document_id=uuid.UUID(int=99),
        filename="leave.md",
        doc_metadata={},
        chunk_index=chunk_id.int,
        section=None,
        page_start=None,
        page_end=None,
        text=f"chunk {chunk_id.int}",
    )


class FakeVectors:
    def __init__(self, hits=(), error: Exception | None = None):
        self.hits = list(hits)
        self.error = error
        self.calls = []

    def search(self, vector, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.hits[: kwargs["limit"]]


class FakeEmbedder:
    def __init__(self):
        self.queries = []

    def embed_query(self, text):
        self.queries.append(text)
        return [0.0] * 4


@pytest.fixture
def fake_db(monkeypatch):
    """PostgreSQL's side: which chunks it confirms (ready, the caller's), keyword hits."""
    state = {"confirmed": set(IDS), "keyword": [], "terms": 3, "scope_ok": True}

    def check_scope(db, owner_id, kb_id, document_id):
        if not state["scope_ok"]:
            raise NotFoundError("Knowledge base not found.")

    def load_passages(db, owner_id, kb_id, chunk_ids, document_id):
        return {i: passage(i) for i in chunk_ids if i in state["confirmed"]}

    monkeypatch.setattr(retrieval, "_check_scope", check_scope)
    monkeypatch.setattr(retrieval, "_load_passages", load_passages)
    monkeypatch.setattr(
        retrieval, "keyword_search", lambda db, **kw: state["keyword"][: kw["limit"]]
    )
    monkeypatch.setattr(retrieval, "count_terms", lambda db, query: state["terms"])
    return state


def run(vectors, mode, *, embedder=None, top_k=5, candidates=20, min_score=None):
    embedder = embedder or FakeEmbedder()
    return retrieval.search(
        None,
        vectors,
        lambda: embedder,
        owner_id=OWNER,
        kb_id=KB,
        query="carry forward",
        mode=mode,
        top_k=top_k,
        candidates=candidates,
        min_score=min_score,
    )


def dense(*pairs):
    return [SearchHit(chunk_id=IDS[i], score=s, payload={}) for i, s in pairs]


def kw(*pairs):
    return [KeywordHit(chunk_id=IDS[i], matched=m, rank=0.5) for i, m in pairs]


def ids(outcome):
    return [IDS.index(r.passage.chunk_id) for r in outcome.results]


def test_semantic_mode_keeps_cosine_order_and_never_runs_keyword(fake_db):
    fake_db["keyword"] = kw((5, 3))
    embedder = FakeEmbedder()
    out = run(FakeVectors(dense((0, 0.9), (1, 0.8), (2, 0.7))), "semantic", embedder=embedder)
    assert ids(out) == [0, 1, 2]
    assert [r.score for r in out.results] == [0.9, 0.8, 0.7]
    assert [r.semantic_rank for r in out.results] == [1, 2, 3]
    assert all(r.keyword_rank is None for r in out.results)
    assert embedder.queries == ["carry forward"]  # the prefix is the Embedder's job


def test_keyword_mode_never_embeds(fake_db):
    fake_db["keyword"] = kw((3, 2), (4, 1))
    embedder = FakeEmbedder()
    vectors = FakeVectors(dense((0, 0.9)))
    out = run(vectors, "keyword", embedder=embedder)
    assert ids(out) == [3, 4]
    assert out.results[0].score == 2.5 and out.results[0].keyword_matched == 2
    assert embedder.queries == [] and vectors.calls == []


def test_hybrid_fuses_both_lists_by_rank(fake_db):
    fake_db["keyword"] = kw((2, 3), (0, 2), (5, 1))
    out = run(FakeVectors(dense((0, 0.9), (1, 0.8), (2, 0.7))), "hybrid")
    # c0: sem 1 + kw 2; c2: sem 3 + kw 1; c1: sem 2 only; c5: kw 3 only
    assert ids(out) == [0, 2, 1, 5]
    first = out.results[0]
    assert first.score == pytest.approx(1 / 61 + 1 / 62)
    assert (first.semantic_rank, first.keyword_rank) == (1, 2)
    assert (first.semantic_score, first.keyword_matched) == (0.9, 2)


def test_top_k_cuts_the_list_and_candidates_is_at_least_top_k(fake_db):
    vectors = FakeVectors(dense(*[(i, 0.9 - i / 10) for i in range(7)]))
    out = run(vectors, "semantic", top_k=2, candidates=20)
    assert ids(out) == [0, 1]
    assert vectors.calls[0]["limit"] == 20  # more candidates than shown
    run(vectors, "semantic", top_k=6, candidates=3)
    assert vectors.calls[1]["limit"] == 6


def test_threshold_drops_weak_semantic_hits_before_fusion(fake_db):
    fake_db["keyword"] = kw((6, 1))
    vectors = FakeVectors(dense((0, 0.81), (1, 0.80), (2, 0.79)))
    assert ids(run(vectors, "semantic", min_score=0.8)) == [0, 1]
    assert ids(run(vectors, "semantic", min_score=0.95)) == []
    # In hybrid the keyword list is untouched by the threshold.
    assert ids(run(vectors, "hybrid", min_score=0.8)) == [0, 6, 1]


def test_chunks_postgresql_does_not_confirm_are_dropped_and_ranks_close_up(fake_db):
    # c1: an orphan point, or a document no longer ready: Qdrant has it, PostgreSQL doesn't.
    fake_db["confirmed"] = set(IDS) - {IDS[1]}
    out = run(FakeVectors(dense((0, 0.9), (1, 0.85), (2, 0.8))), "semantic")
    assert ids(out) == [0, 2]
    assert [r.semantic_rank for r in out.results] == [1, 2]


def test_semantic_mode_fails_with_503_when_qdrant_is_down(fake_db):
    with pytest.raises(ServiceUnavailableError):
        run(FakeVectors(error=ConnectionError("refused")), "semantic")


def test_hybrid_falls_back_to_keyword_results_with_a_notice(fake_db):
    fake_db["keyword"] = kw((3, 2), (4, 1))
    out = run(FakeVectors(error=ConnectionError("refused")), "hybrid")
    assert ids(out) == [3, 4]
    assert out.notice == HYBRID_DEGRADED
    assert out.results[0].score == pytest.approx(1 / 61)


def test_a_failing_model_is_handled_like_a_failing_qdrant(fake_db):
    class Broken:
        def embed_query(self, text):
            raise RuntimeError("model not loaded")

    fake_db["keyword"] = kw((3, 1))
    assert run(FakeVectors(), "hybrid", embedder=Broken()).notice == HYBRID_DEGRADED


def test_only_common_words_get_a_notice_in_keyword_mode(fake_db):
    fake_db["terms"] = 0
    out = run(FakeVectors(), "keyword")
    assert (out.results, out.query_terms, out.notice) == ([], 0, ONLY_COMMON_WORDS)
    fake_db["terms"] = 2  # real words that simply match nothing: no notice
    assert run(FakeVectors(), "keyword").notice is None


def test_not_your_knowledge_base_is_404_in_every_mode(fake_db):
    fake_db["scope_ok"] = False
    for mode in ("semantic", "keyword", "hybrid"):
        with pytest.raises(NotFoundError):
            run(FakeVectors(dense((0, 0.9))), mode)


def test_timings_are_reported_per_stage(fake_db):
    fake_db["keyword"] = kw((0, 1))
    out = run(FakeVectors(dense((0, 0.9))), "hybrid")
    assert set(out.timings_ms) == {
        "embed",
        "vector_search",
        "connect_and_scope_check",
        "keyword_search",
        "load_passages",
        "total",
    }


# --- the request body --------------------------------------------------------------------------


def test_query_is_trimmed_and_whitespace_collapsed():
    body = SearchRequest(query="  carry \n\t forward  ")
    assert body.query == "carry forward"
    assert (body.mode, body.top_k, body.min_score) == ("hybrid", 10, None)


@pytest.mark.parametrize(
    "changes",
    [
        {"query": "   "},
        {"query": "a\x00b"},
        {"query": "x" * (QUERY_MAX + 1)},
        {"mode": "fuzzy"},
        {"top_k": 0},
        {"top_k": 51},
        {"min_score": -0.1},
        {"min_score": 1.5},
        {"document_id": "not-a-uuid"},
    ],
)
def test_invalid_requests_are_rejected(changes):
    with pytest.raises(ValidationError):
        SearchRequest(**{"query": "leave", **changes})


# --- route guards (answer before any database work) ----------------------------------------------


def test_search_needs_a_session(client):
    response = client.post(f"/api/knowledge-bases/{uuid.uuid4()}/search", json={"query": "x"})
    assert response.status_code == 401


def test_search_with_a_malformed_kb_id_is_not_found(client):
    client.cookies.set(SESSION_COOKIE, create_access_token(uuid.uuid4(), FAKE_JWT_SECRET, 5))
    response = client.post("/api/knowledge-bases/nope/search", json={"query": "x"})
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Knowledge base not found."


def test_an_empty_query_is_a_validation_error(client):
    client.cookies.set(SESSION_COOKIE, create_access_token(uuid.uuid4(), FAKE_JWT_SECRET, 5))
    response = client.post(f"/api/knowledge-bases/{uuid.uuid4()}/search", json={"query": " "})
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["message"] == "Enter something to search for"
