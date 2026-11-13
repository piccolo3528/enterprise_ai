"""Finding the passages that answer a query: semantic, keyword or hybrid (ARCHITECTURE §4.3).

    semantic  embed the query -> Qdrant: nearest chunk vectors (cosine), owner + KB filtered
    keyword   PostgreSQL full-text search (keyword_search.py)
    hybrid    both, fused by Reciprocal Rank Fusion

Rules:
- **PostgreSQL has the last word.** Qdrant returns chunk ids; the text and metadata are read from
  PostgreSQL, and only chunks of `ready` documents in a knowledge base the caller owns are kept.
  So an orphan point (L40) or a document being reprocessed or deleted never shows up, and
  `ready` keeps meaning "searchable".
- **Top-K.** Each retriever returns `candidates` hits (at least RETRIEVAL_TOP_K, 20): hybrid
  needs more than K from each side to fuse well, and dropped hits (above) leave room to refill.
  The caller gets `top_k`.
- **Threshold.** `min_score` is a minimum cosine similarity. It applies to the semantic list (in
  semantic and hybrid mode) before anything else. It doesn't apply to keyword scores, which
  measure something else (matched words), nor to RRF scores, which only encode ranks.
- **Concurrency.** The semantic side (embedding ~30 ms + Qdrant ~150 ms) runs in a worker thread
  while this thread checks ownership and runs the keyword query on PostgreSQL.
- **Degrading.** If Qdrant or the model is unavailable, semantic mode fails with 503 and hybrid
  mode returns the keyword results with a notice saying so.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable, Hashable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ServiceUnavailableError
from app.models import Chunk, Document, KnowledgeBase
from app.services.documents import DOCUMENT_NOT_FOUND
from app.services.embeddings import Embedder
from app.services.keyword_search import KeywordHit, count_terms, keyword_search
from app.services.knowledge_bases import NOT_FOUND as KB_NOT_FOUND
from app.services.vector_store import SearchHit, VectorStore

logger = logging.getLogger("app.retrieval")

Mode = Literal["semantic", "keyword", "hybrid"]

RRF_K = 60  # the constant from the original RRF paper (Cormack et al., 2009)

SEMANTIC_UNAVAILABLE = (
    "Semantic search is unavailable right now (the vector database can't be reached). "
    "Keyword search still works."
)
HYBRID_DEGRADED = "Semantic search is unavailable right now, so these are keyword matches only."
ONLY_COMMON_WORDS = (
    'Keyword search ignores very common words (like "the", "of", "how"), and your search '
    "has only those. Try semantic search, or add a more specific word."
)

# The semantic side's thread. Shared by all requests, so a burst of searches can't create
# threads without limit.
_dense_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="dense-search")


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[Hashable]], *, k: int = RRF_K
) -> list[tuple[Hashable, float]]:
    """Fuse several best-first rankings into one: score(d) = Σ 1 / (k + rank_i(d)).

    Uses ranks only, never the retrievers' scores: a cosine of 0.8 and a keyword rank of 0.3
    aren't on the same scale, but "2nd place" means the same in both lists. An item found by
    both retrievers collects two terms, so agreement is rewarded. k = 60 flattens the curve:
    rank 1 vs rank 2 is 1/61 vs 1/62, so one list's top item can't dominate on its own.

    Ties keep first-seen order (Python's sort is stable), which makes the result deterministic.
    """
    scores: dict[Hashable, float] = {}
    for ranking in rankings:
        seen: set[Hashable] = set()
        for rank, item in enumerate(ranking, start=1):
            if item in seen:  # a list should not repeat an item; count only its best rank
                continue
            seen.add(item)
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


@dataclass(frozen=True)
class Passage:
    """A chunk with what a search result shows about it, read from PostgreSQL."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    doc_metadata: dict[str, Any]
    chunk_index: int
    section: str | None
    page_start: int | None
    page_end: int | None
    text: str


@dataclass
class SearchResult:
    passage: Passage
    score: float  # the mode's own score: cosine, keyword score or RRF score
    semantic_rank: int | None = None
    semantic_score: float | None = None
    keyword_rank: int | None = None
    keyword_score: float | None = None
    keyword_matched: int | None = None


@dataclass
class SearchOutcome:
    mode: Mode
    results: list[SearchResult]
    query_terms: int | None = None  # searchable words, counted when keyword mode found none
    notice: str | None = None
    timings_ms: dict[str, float] = field(default_factory=dict)


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def _check_scope(
    db: Session, owner_id: uuid.UUID, kb_id: uuid.UUID, document_id: uuid.UUID | None
) -> None:
    """404 unless the caller owns the KB and (if given) the document is in it. One query."""
    found_document = (
        select(Document.id)
        .where(Document.id == document_id, Document.kb_id == KnowledgeBase.id)
        .correlate(KnowledgeBase)
        .exists()
        if document_id
        else None
    )
    columns = [KnowledgeBase.id] + ([found_document] if found_document is not None else [])
    row = db.execute(
        select(*columns).where(KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == owner_id)
    ).first()
    if row is None:
        raise NotFoundError(KB_NOT_FOUND)
    if document_id and not row[1]:
        raise NotFoundError(DOCUMENT_NOT_FOUND)


def _load_passages(
    db: Session,
    owner_id: uuid.UUID,
    kb_id: uuid.UUID,
    chunk_ids: set[uuid.UUID],
    document_id: uuid.UUID | None,
) -> dict[uuid.UUID, Passage]:
    """Text + metadata for these chunks, only from ready documents in the caller's KB."""
    if not chunk_ids:
        return {}
    conditions = [
        Chunk.id.in_(chunk_ids),
        Chunk.kb_id == kb_id,
        KnowledgeBase.owner_id == owner_id,
        Document.status == "ready",
    ]
    if document_id:
        conditions.append(Chunk.document_id == document_id)
    rows = db.execute(
        select(
            Chunk.id,
            Chunk.document_id,
            Document.original_filename,
            Document.doc_metadata,
            Chunk.chunk_index,
            Chunk.section,
            Chunk.page_start,
            Chunk.page_end,
            Chunk.text,
        )
        .join(Document, Document.id == Chunk.document_id)
        .join(KnowledgeBase, KnowledgeBase.id == Chunk.kb_id)
        .where(*conditions)
    ).all()
    return {row[0]: Passage(*row) for row in rows}


def search(
    db: Session,
    vectors: VectorStore,
    embedder: Callable[[], Embedder],
    *,
    owner_id: uuid.UUID,
    kb_id: uuid.UUID,
    query: str,
    mode: Mode,
    top_k: int,
    candidates: int,
    min_score: float | None = None,
    document_id: uuid.UUID | None = None,
) -> SearchOutcome:
    """Search one knowledge base. `embedder` is called only if the semantic side runs (so
    keyword search works even while the model is still loading at startup)."""
    started = time.perf_counter()
    candidates = max(candidates, top_k)
    timings: dict[str, float] = {}
    outcome = SearchOutcome(mode=mode, results=[], timings_ms=timings)

    def dense() -> list[SearchHit]:
        t = time.perf_counter()
        vector = embedder().embed_query(query)
        timings["embed"] = _ms(t)
        t = time.perf_counter()
        hits = vectors.search(
            vector, owner_id=owner_id, kb_id=kb_id, limit=candidates, document_id=document_id
        )
        timings["vector_search"] = _ms(t)
        return hits

    # Start the semantic side first, so it overlaps with the PostgreSQL work below.
    dense_future: Future[list[SearchHit]] | None = (
        _dense_pool.submit(dense) if mode in ("semantic", "hybrid") else None
    )
    try:
        # The request's first query, so its time includes taking a connection from the pool
        # and its pre-ping (D23), plus a new TLS connection if the pooled one had expired:
        # measured in Chrome, ~115 ms warm, 370-520 ms after a few idle minutes.
        t = time.perf_counter()
        _check_scope(db, owner_id, kb_id, document_id)
        timings["connect_and_scope_check"] = _ms(t)

        keyword_hits: list[KeywordHit] = []
        if mode in ("keyword", "hybrid"):
            t = time.perf_counter()
            keyword_hits = keyword_search(
                db,
                owner_id=owner_id,
                kb_id=kb_id,
                query=query,
                limit=candidates,
                document_id=document_id,
            )
            timings["keyword_search"] = _ms(t)
            if mode == "keyword" and not keyword_hits:
                # Nothing matched: was there anything to match? (one more query, only here)
                outcome.query_terms = count_terms(db, query)

        dense_hits: list[SearchHit] = []
        if dense_future is not None:
            try:
                dense_hits = dense_future.result()
            except Exception as exc:  # noqa: BLE001 - Qdrant/model down: degrade or 503
                logger.warning("Semantic search failed (%s)", type(exc).__name__)
                if mode == "semantic":
                    raise ServiceUnavailableError(SEMANTIC_UNAVAILABLE) from None
                outcome.notice = HYBRID_DEGRADED
    finally:
        if dense_future is not None:
            dense_future.cancel()  # only has an effect if it never started (e.g. a 404 above)

    if min_score is not None:
        dense_hits = [hit for hit in dense_hits if hit.score >= min_score]

    t = time.perf_counter()
    passages = _load_passages(
        db,
        owner_id,
        kb_id,
        {hit.chunk_id for hit in dense_hits} | {hit.chunk_id for hit in keyword_hits},
        document_id,
    )
    timings["load_passages"] = _ms(t)

    # Ranks are counted after dropping what PostgreSQL didn't confirm.
    dense_hits = [hit for hit in dense_hits if hit.chunk_id in passages]
    keyword_hits = [hit for hit in keyword_hits if hit.chunk_id in passages]
    dense_by_id = {hit.chunk_id: (rank, hit) for rank, hit in enumerate(dense_hits, start=1)}
    keyword_by_id = {hit.chunk_id: (rank, hit) for rank, hit in enumerate(keyword_hits, start=1)}

    if mode == "semantic":
        ranked = [(hit.chunk_id, hit.score) for hit in dense_hits]
    elif mode == "keyword":
        ranked = [(hit.chunk_id, hit.score) for hit in keyword_hits]
    else:
        ranked = reciprocal_rank_fusion(
            [[hit.chunk_id for hit in dense_hits], [hit.chunk_id for hit in keyword_hits]]
        )

    for chunk_id, score in ranked[:top_k]:
        result = SearchResult(passage=passages[chunk_id], score=score)
        if chunk_id in dense_by_id:
            rank, hit = dense_by_id[chunk_id]
            result.semantic_rank, result.semantic_score = rank, hit.score
        if chunk_id in keyword_by_id:
            rank, hit = keyword_by_id[chunk_id]
            result.keyword_rank, result.keyword_score = rank, hit.score
            result.keyword_matched = hit.matched
        outcome.results.append(result)

    if mode == "keyword" and outcome.query_terms == 0:
        outcome.notice = ONLY_COMMON_WORDS
    timings["total"] = _ms(started)
    # The query itself is never logged: it is user content.
    logger.info(
        "Search mode=%s query_chars=%d results=%d timings_ms=%s",
        mode,
        len(query),
        len(outcome.results),
        timings,
    )
    return outcome
