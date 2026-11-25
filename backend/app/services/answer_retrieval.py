"""Choosing the passages an answer is built from (M14): hybrid search, then optional stages.

    question (+ extra phrasings, multi-query) ──► hybrid search each, fuse by RRF   (retrieval.py)
          ▼
    amendments: a retrieved document's current amendments are searched too   (S4 rule 3)
          ▼
    rerank: the cross-encoder re-orders the pool                              (reranker.py)
          ▼
    versions: outdated passages below current ones, unless the question needs them (S4 rules 1-2)
          ▼
    the best `max_sources`; amendment passages keep their place (inserted after their base)

Every stage is switched by `RetrievalSettings`, so the evaluation (evaluation/compare_retrieval.py)
measures exactly this code with stages on and off, and the app turns on what the numbers support.
Version rules run *after* reranking: the cross-encoder can't know a passage is outdated and
would otherwise put it back on top.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, KnowledgeBase
from app.services import retrieval
from app.services.embeddings import Embedder
from app.services.reranker import Reranker, rerank
from app.services.retrieval import SearchOutcome, SearchResult, reciprocal_rank_fusion
from app.services.vector_store import VectorStore
from app.services.version_rules import VersionMode, amendments_to_fetch, prefer_current

AMENDMENT_PASSAGES = 2  # passages taken from each amendment


@dataclass(frozen=True)
class RetrievalSettings:
    candidates: int = 20  # per retriever (RETRIEVAL_TOP_K)
    pool: int = 10  # hybrid results considered (reranked when on); >= max_sources
    max_sources: int = 10  # passages handed to the context builder
    rerank: bool = False
    rerank_min_score: float | None = None  # drop passages the cross-encoder scores below this
    # True: fuse the cross-encoder's order with the hybrid order by RRF instead of replacing it
    rerank_fusion: bool = False
    version_mode: VersionMode = "off"
    amendments: bool = False


@dataclass
class Retrieved:
    outcome: SearchOutcome  # results = the chosen passages, best first
    queries: int = 1
    amendment_passages: int = 0
    dropped_outdated: int = 0
    timings_ms: dict[str, float] = field(default_factory=dict)


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def _amendment_documents(
    db: Session, owner_id: uuid.UUID, kb_id: uuid.UUID | None
) -> list[tuple[uuid.UUID, dict]]:
    """(id, front matter) of the KB's (or, with None, all the owner's) ready documents that
    amend another one. One query."""
    conditions = [
        KnowledgeBase.owner_id == owner_id,
        Document.status == "ready",
        Document.doc_metadata["amends"].as_string().is_not(None),
    ]
    if kb_id is not None:
        conditions.append(Document.kb_id == kb_id)
    rows = db.execute(
        select(Document.id, Document.doc_metadata)
        .join(KnowledgeBase, KnowledgeBase.id == Document.kb_id)
        .where(*conditions)
    ).all()
    return [(row[0], row[1] or {}) for row in rows]


def retrieve(
    db: Session,
    vectors: VectorStore,
    embedder: Callable[[], Embedder],
    reranker: Callable[[], Reranker] | None,
    *,
    owner_id: uuid.UUID,
    kb_id: uuid.UUID | None,
    query: str,
    settings: RetrievalSettings,
    extra_queries: Sequence[str] = (),
    document_id: uuid.UUID | None = None,
) -> Retrieved:
    started = time.perf_counter()
    timings: dict[str, float] = {}
    pool = max(settings.pool, settings.max_sources)

    def search(text: str, doc: uuid.UUID | None, top_k: int) -> SearchOutcome:
        return retrieval.search(
            db, vectors, embedder, owner_id=owner_id, kb_id=kb_id, query=text, mode="hybrid",
            top_k=top_k, candidates=max(settings.candidates, top_k), document_id=doc,
        )  # fmt: skip

    # 1. hybrid search, once per phrasing; several phrasings are fused by rank (RRF)
    t = time.perf_counter()
    outcomes = [search(q, document_id, pool) for q in [query, *extra_queries]]
    main = outcomes[0]
    if len(outcomes) > 1:
        by_id = {r.passage.chunk_id: r for o in outcomes for r in reversed(o.results)}
        fused = reciprocal_rank_fusion([[r.passage.chunk_id for r in o.results] for o in outcomes])
        results = [by_id[chunk_id] for chunk_id, _ in fused][:pool]
    else:
        results = list(main.results)
    timings["search"] = _ms(t)
    notice = next((o.notice for o in outcomes if o.notice), None)
    retrieved = Retrieved(
        outcome=SearchOutcome("hybrid", [], notice=notice, timings_ms=timings),
        queries=len(outcomes),
        timings_ms=timings,  # the same dict: later stages add to it
    )

    # 2. amendments of the retrieved documents (not when the user limited the search to one)
    extra: list[SearchResult] = []
    if settings.amendments and results and document_id is None:
        t = time.perf_counter()
        present = {r.passage.chunk_id for r in results}
        for amendment_id in amendments_to_fetch(results, _amendment_documents(db, owner_id, kb_id)):
            found = search(query, amendment_id, AMENDMENT_PASSAGES).results
            extra.extend(r for r in found if r.passage.chunk_id not in present)
        retrieved.amendment_passages = len(extra)
        timings["amendments"] = _ms(t)

    # 3. rerank the pool (amendment passages are scored too, for the record and the panel)
    if settings.rerank and reranker is not None and results:
        t = time.perf_counter()
        model = reranker()
        timings["load_reranker"] = _ms(t)
        reranked, timings["rerank"] = rerank(
            model, query, results, top_n=len(results), min_score=settings.rerank_min_score
        )
        if settings.rerank_fusion:
            by_id = {r.passage.chunk_id: r for r in reranked}
            fused = reciprocal_rank_fusion(
                [[r.passage.chunk_id for r in results if r.passage.chunk_id in by_id],
                 [r.passage.chunk_id for r in reranked]]
            )  # fmt: skip
            reranked = [by_id[chunk_id] for chunk_id, _ in fused]
        results = reranked
        if extra:
            extra, _ = rerank(model, query, extra, top_n=len(extra))

    # 4. current versions first (or only)
    before = len(results)
    results = prefer_current(results, query, mode=settings.version_mode)
    retrieved.dropped_outdated = before - len(results)

    # 5. the best max_sources, keeping room for the amendment passages
    chosen = results[: max(0, settings.max_sources - len(extra))]
    inserted: dict[str, int] = {}  # base -> passages already placed after it (keeps their order)
    for passage in extra:
        base = str((passage.passage.doc_metadata or {}).get("amends") or "")
        position = next(
            (i + 1 for i, r in enumerate(chosen)
             if f"{(m := r.passage.doc_metadata or {}).get('document_id')} v{m.get('version')}"
             == base),
            len(chosen),
        )  # fmt: skip
        chosen.insert(position + inserted.get(base, 0), passage)
        inserted[base] = inserted.get(base, 0) + 1
    retrieved.outcome.results = chosen[: settings.max_sources]
    timings["retrieval_total"] = _ms(started)
    return retrieved
