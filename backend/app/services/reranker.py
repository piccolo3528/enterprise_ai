"""Second-stage ranking with a cross-encoder (ARCHITECTURE §4.4, M14).

The embedding model (a *bi-encoder*) turns the question and each passage into vectors
separately, so neither text "sees" the other: fast enough for the whole collection, but coarse.
A *cross-encoder* reads (question, passage) together and outputs one relevance score: much more
precise, far too slow to run over everything. So retrieval gathers candidates cheaply (hybrid
search) and the cross-encoder re-orders only those.

Model: `cross-encoder/ms-marco-MiniLM-L-6-v2` (RERANKER_MODEL), local CPU, loaded once per
process. Its scores are logits (unbounded; higher = more relevant), comparable across passages
of one question but, as M12 measured, no use as an "is the answer here?" threshold (D62).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from dataclasses import replace
from typing import Protocol

from app.services.retrieval import SearchResult

BATCH_SIZE = 16


class PairScorer(Protocol):
    """The part of sentence-transformers' CrossEncoder we use (tests pass a fake)."""

    def predict(self, sentences: list[tuple[str, str]], **kwargs): ...


class Reranker:
    def __init__(self, model: PairScorer, *, batch_size: int = BATCH_SIZE) -> None:
        self._model = model
        self.batch_size = batch_size

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        if not texts:
            return []
        scores = self._model.predict(
            [(query, text) for text in texts],
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [float(s) for s in scores]


def rerank(
    reranker: Reranker,
    query: str,
    results: Sequence[SearchResult],
    *,
    top_n: int,
    min_score: float | None = None,
) -> tuple[list[SearchResult], float]:
    """The `results` re-ordered by cross-encoder score (best first), at most `top_n`, without
    those below `min_score` (if given). Ties keep the retrieval order. Returns (results, ms)."""
    started = time.perf_counter()
    scores = reranker.score(query, [r.passage.text for r in results])
    ranked = sorted(
        (replace(r, rerank_score=s) for r, s in zip(results, scores, strict=True)),
        key=lambda r: r.rerank_score,
        reverse=True,
    )
    if min_score is not None:
        ranked = [r for r in ranked if r.rerank_score >= min_score]
    return ranked[:top_n], round((time.perf_counter() - started) * 1000, 1)


def load_reranker(model_name: str, *, local_only: bool = False) -> Reranker:
    from sentence_transformers import CrossEncoder  # imports PyTorch (shared with embeddings)

    try:
        model = CrossEncoder(model_name, device="cpu", local_files_only=True)
    except Exception:  # noqa: BLE001 - not cached yet (scripts/download_models.py does it)
        if local_only:
            raise
        model = CrossEncoder(model_name, device="cpu")
    return Reranker(model)


_cache: dict[str, Reranker] = {}
_lock = threading.Lock()


def get_reranker(model_name: str) -> Reranker:
    """One model per process (the lock guards loading only, as for the embedder)."""
    with _lock:
        if model_name not in _cache:
            _cache[model_name] = load_reranker(model_name)
        return _cache[model_name]
