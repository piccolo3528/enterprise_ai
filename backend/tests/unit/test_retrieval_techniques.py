"""M14: reranking, version-aware retrieval, amendments, multi-query parsing and the retrieval
pipeline's stage order, with the models and the databases replaced by fakes."""

from __future__ import annotations

import json
import uuid
from datetime import date

from app.services import answer_retrieval
from app.services.answer_retrieval import RetrievalSettings, retrieve
from app.services.llm.prompts import MULTI_QUERY_COUNT, parse_search_queries
from app.services.reranker import Reranker, rerank
from app.services.retrieval import SearchOutcome
from app.services.version_rules import (
    amendments_to_fetch,
    in_force_during,
    is_current,
    is_historical,
    mentioned_dates,
    prefer_current,
)
from tests.unit.test_answering import passage, results

V3 = {"document_id": "NX-HR-002", "version": "3.0", "status": "current",
      "effective_date": "2026-04-01", "superseded_date": None}  # fmt: skip
V2 = {"document_id": "NX-HR-002", "version": "2.0", "status": "superseded",
      "effective_date": "2024-04-01", "superseded_date": "2026-03-31"}  # fmt: skip
BASE = {"document_id": "NX-FIN-001", "version": "2.0", "status": "current"}
AMENDMENT = {"document_id": "NX-FIN-001-A1", "version": "1.0", "status": "current",
             "amends": "NX-FIN-001 v2.0"}  # fmt: skip


# --- reranking -----------------------------------------------------------------------------------


class FakeCrossEncoder:
    """Scores a pair by how many query words the passage contains."""

    def __init__(self):
        self.calls = 0

    def predict(self, pairs, **kwargs):
        self.calls += 1
        return [float(sum(w in text for w in query.split())) for query, text in pairs]


def test_rerank_orders_by_the_cross_encoder_and_keeps_ties_in_retrieval_order():
    ranked = results(passage(1, text="nothing"), passage(2, text="carry forward leave"),
                     passage(3, text="leave"), passage(4, text="leave rules"))  # fmt: skip
    out, ms = rerank(Reranker(FakeCrossEncoder()), "carry forward leave", ranked, top_n=3)
    assert [r.passage.chunk_id.int for r in out] == [2, 3, 4]  # 3 and 4 tie: retrieval order
    assert [r.rerank_score for r in out] == [3.0, 1.0, 1.0] and ms >= 0
    assert ranked[0].rerank_score is None  # the input isn't modified


def test_a_rerank_threshold_drops_low_scoring_passages():
    ranked = results(passage(1, text="nothing"), passage(2, text="leave"))
    out, _ = rerank(Reranker(FakeCrossEncoder()), "leave", ranked, top_n=10, min_score=0.5)
    assert [r.passage.chunk_id.int for r in out] == [2]


def test_no_passages_means_no_model_call():
    model = FakeCrossEncoder()
    assert Reranker(model).score("q", []) == [] and model.calls == 0


# --- versions ------------------------------------------------------------------------------------


def test_dates_in_a_question_become_intervals():
    assert mentioned_dates("On 31 December 2025 I had 28 days") == [
        (date(2025, 12, 31), date(2025, 12, 31))]  # fmt: skip
    assert mentioned_dates("a hotel in Kochi in November 2025") == [
        (date(2025, 11, 1), date(2025, 11, 30))]  # fmt: skip
    assert mentioned_dates("rules in 2024, or from 2026-04-01?") == [
        (date(2026, 4, 1), date(2026, 4, 1)), (date(2024, 1, 1), date(2024, 12, 31))]  # fmt: skip
    assert mentioned_dates("March 3, 2026") == [(date(2026, 3, 3), date(2026, 3, 3))]
    assert mentioned_dates("How many days of leave do I get?") == []
    assert mentioned_dates("31 February 2025") == [(date(2025, 2, 1), date(2025, 2, 28))]


def test_historical_wording():
    historical = (
        "What was the previous carry-forward limit?",
        "What did v2.0 say?",
        "the old policy on encashment",
        "Is that still allowed or no longer?",
    )
    for text in historical:
        assert is_historical(text), text
    for text in ("How many days can I carry forward?", "What is the current hotel limit?",
                 "Can I work from home on Fridays?"):  # fmt: skip
        assert not is_historical(text), text


def test_in_force_during_uses_the_validity_window():
    dec_2025 = [(date(2025, 12, 31), date(2025, 12, 31))]
    assert in_force_during(V2, dec_2025) and not in_force_during(V3, dec_2025)
    assert in_force_during(V3, [(date(2027, 1, 1), date(2027, 12, 31))])  # open end
    assert not in_force_during({"status": "superseded"}, dec_2025)  # no dates: unknown
    assert is_current({}) and is_current(V3) and not is_current(V2)  # no front matter = current


def ranked_versions():
    return results(passage(1, meta=V2), passage(2, meta=V3), passage(3, meta=V2),
                   passage(4))  # fmt: skip


def ids(rs):
    return [r.passage.chunk_id.int for r in rs]


def test_outdated_passages_are_demoted_or_filtered():
    question = "How many days can I carry forward?"
    assert ids(prefer_current(ranked_versions(), question, mode="demote")) == [2, 4, 1, 3]
    assert ids(prefer_current(ranked_versions(), question, mode="filter")) == [2, 4]
    assert ids(prefer_current(ranked_versions(), question, mode="off")) == [1, 2, 3, 4]


def test_outdated_passages_stay_when_the_question_needs_them():
    assert ids(prefer_current(ranked_versions(), "What was the previous limit?",
                              mode="filter")) == [1, 2, 3, 4]  # fmt: skip
    # Q042: an event dated inside v2.0's window keeps v2.0 in place
    q042 = "On 31 December 2025 I had 28 days of unused Earned Leave. How many could I carry?"
    assert ids(prefer_current(ranked_versions(), q042, mode="demote")) == [1, 2, 3, 4]


def test_only_amendments_of_retrieved_documents_are_fetched():
    retrieved = results(passage(1, meta=BASE), passage(2, meta=V3))
    amendments = [("a1", AMENDMENT), ("old", {**AMENDMENT, "status": "superseded"}),
                  ("other", {**AMENDMENT, "amends": "NX-IT-001 v3.1"})]  # fmt: skip
    assert amendments_to_fetch(retrieved, amendments) == ["a1"]
    assert amendments_to_fetch(results(passage(2, meta=V3)), amendments) == []


# --- the pipeline --------------------------------------------------------------------------------


class FakeSearch:
    """retrieval.search stand-in: per (query, document_id) a fixed result list; records calls."""

    def __init__(self, table):
        self.table, self.calls = table, []

    def __call__(self, db, vectors, embedder, *, query, document_id, top_k, **kwargs):
        self.calls.append((query, document_id, top_k))
        return SearchOutcome("hybrid", list(self.table.get((query, document_id), []))[:top_k])


def run(monkeypatch, table, settings, *, amendments=(), query="q", **kwargs):
    fake = FakeSearch(table)
    monkeypatch.setattr(answer_retrieval.retrieval, "search", fake)
    monkeypatch.setattr(answer_retrieval, "_amendment_documents", lambda *a: list(amendments))
    model = FakeCrossEncoder()
    got = retrieve(None, None, None, lambda: Reranker(model), owner_id=uuid.uuid4(),
                   kb_id=uuid.uuid4(), query=query, settings=settings, **kwargs)  # fmt: skip
    return got, fake, model


def test_with_every_stage_off_it_is_plain_hybrid_search(monkeypatch):
    table = {("q", None): results(*(passage(i) for i in range(1, 15)))}
    got, fake, model = run(monkeypatch, table, RetrievalSettings())
    assert ids(got.outcome.results) == list(range(1, 11)) and model.calls == 0
    assert fake.calls == [("q", None, 10)]


def test_stages_run_in_order_rerank_then_versions_and_amendments_keep_a_place(monkeypatch):
    base = passage(1, text="hotel", meta=BASE)
    old = passage(2, text="hotel limit", meta=V2)  # the cross-encoder likes it best
    other = passage(3, text="limit", meta=V3)
    amended = passage(9, text="hotel", meta=AMENDMENT)
    table = {("hotel limit", None): results(base, old, other),
             ("hotel limit", "a1"): results(amended)}  # fmt: skip
    settings = RetrievalSettings(pool=20, max_sources=3, rerank=True, version_mode="demote",
                                 amendments=True)  # fmt: skip
    got, fake, _ = run(monkeypatch, table, settings, amendments=[("a1", AMENDMENT)],
                       query="hotel limit")  # fmt: skip
    # reranked: old (2) > base (1) = other (1); demoted: old last; the amendment follows its base
    # and keeps its place, so the last of the 3 slots goes to it, not to the outdated passage
    assert ids(got.outcome.results) == [1, 9, 3]
    assert got.amendment_passages == 1 and fake.calls[1] == ("hotel limit", "a1", 2)
    assert {"search", "amendments", "rerank", "retrieval_total"} <= set(got.timings_ms)


def test_several_phrasings_are_fused_by_rank(monkeypatch):
    table = {("q", None): results(passage(1), passage(2)),
             ("other words", None): results(passage(3), passage(2))}  # fmt: skip
    got, fake, _ = run(monkeypatch, table, RetrievalSettings(), extra_queries=["other words"])
    assert ids(got.outcome.results)[0] == 2  # found by both phrasings
    assert set(ids(got.outcome.results)) == {1, 2, 3} and got.queries == 2


def test_a_document_filter_skips_amendments(monkeypatch):
    doc = uuid.uuid4()
    table = {("q", doc): results(passage(1, meta=BASE))}
    got, fake, _ = run(monkeypatch, table, RetrievalSettings(amendments=True),
                       amendments=[("a1", AMENDMENT)], document_id=doc)  # fmt: skip
    assert fake.calls == [("q", doc, 10)] and got.amendment_passages == 0


# --- multi-query parsing -------------------------------------------------------------------------


def test_search_queries_are_parsed_deduplicated_and_capped():
    reply = json.dumps({"standalone_question": "Can annual leave be carried forward?",
                        "search_queries": ["carry forward unused annual leave",
                                           "Carry forward unused annual leave", "",
                                           "leave lapse at year end", "third", 7]})  # fmt: skip
    standalone, queries = parse_search_queries(reply, max_chars=1000)
    assert standalone == "Can annual leave be carried forward?"
    assert queries == ["carry forward unused annual leave", "leave lapse at year end"]
    assert len(queries) <= MULTI_QUERY_COUNT
    assert parse_search_queries("not json", max_chars=1000) == (None, [])


def test_fused_rerank_keeps_the_hybrid_order_in_the_vote(monkeypatch):
    # hybrid order 1, 2, 3; the cross-encoder prefers 3 (two query words), then 2, then 1
    table = {("leave rules", None): results(passage(1, text="x"), passage(2, text="leave"),
                                             passage(3, text="leave rules"))}  # fmt: skip
    plain = RetrievalSettings(pool=20, rerank=True)
    got, _, _ = run(monkeypatch, table, plain, query="leave rules")
    assert ids(got.outcome.results) == [3, 2, 1]
    fused = RetrievalSettings(pool=20, rerank=True, rerank_fusion=True)
    got, _, _ = run(monkeypatch, table, fused, query="leave rules")
    # RRF of [1, 2, 3] and [3, 2, 1]: 1/61 + 1/63 (0.03227) beats 2/62 (0.03226) for 2;
    # 1 and 3 tie and keep first-seen order
    assert ids(got.outcome.results) == [1, 3, 2]
