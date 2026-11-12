"""Turning text into vectors with the local embedding model (bge-small-en-v1.5, 384 dimensions).

Three rules (ARCHITECTURE §4.2):
- **Load once.** Importing PyTorch + loading the model takes ~25 s on this laptop, so one model
  per process is created at startup (warm-up) and shared by every job and request.
- **Normalize.** Every vector has length 1, so cosine similarity = dot product, which is what
  Qdrant's cosine distance relies on.
- **Asymmetric prefix.** BGE was trained with an instruction in front of *queries* only:
  "Represent this sentence for searching relevant passages: ". Documents are embedded as they
  are. Adding it to both sides, or leaving it off queries, lowers retrieval quality.

Measured on this laptop (12 CPUs, M9): ~0.37 ms per token, so a 400-token chunk takes ~150 ms
and a query ~30 ms. Batch size barely changes speed on CPU (4..32: 144-159 ms per 400-token
chunk, within noise); batches exist to bound memory. No lock around the model: with a lock, a
search waited 4-13 s behind a document being embedded (Python locks aren't fair); without one,
searches took 129 ms median while a 96-chunk document was embedded, with no errors.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Sequence
from typing import Protocol

BATCH_SIZE = 16

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def query_prefix_for(model_name: str) -> str:
    """The instruction BGE's English models expect in front of queries; other models: none."""
    name = model_name.lower()
    return BGE_QUERY_PREFIX if name.startswith("baai/bge-") and "-en" in name else ""


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """cos θ = a·b / (‖a‖ ‖b‖), written out by hand.

    1 = same direction, 0 = unrelated (orthogonal), -1 = opposite. Only the angle matters, not
    the length, which is why normalized vectors (length 1) make it a plain dot product.
    """
    if len(a) != len(b):
        raise ValueError(f"vectors have different lengths ({len(a)} and {len(b)})")
    dot = math.fsum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(math.fsum(x * x for x in a))
    norm_b = math.sqrt(math.fsum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        raise ValueError("cosine similarity is undefined for a zero vector")
    return dot / (norm_a * norm_b)


class EncoderModel(Protocol):
    """The part of SentenceTransformer we use (tests pass a fake)."""

    def encode(self, sentences: list[str], **kwargs): ...

    def get_embedding_dimension(self) -> int | None: ...


class Embedder:
    def __init__(
        self, model: EncoderModel, *, query_prefix: str = "", batch_size: int = BATCH_SIZE
    ) -> None:
        self._model = model
        self.query_prefix = query_prefix
        self.batch_size = batch_size
        self.dimension: int = model.get_embedding_dimension() or 0

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Chunk texts, exactly as stored (the context header included), without a prefix."""
        return self._encode(list(texts)) if texts else []

    def embed_query(self, text: str) -> list[float]:
        return self._encode([self.query_prefix + text])[0]


def load_embedder(model_name: str, *, local_only: bool = False) -> Embedder:
    """Build the real model on CPU. `local_only=True` never touches the network."""
    from sentence_transformers import SentenceTransformer  # imports PyTorch: ~25 s cold

    try:
        model = SentenceTransformer(model_name, device="cpu", local_files_only=True)
    except Exception:  # noqa: BLE001 - not cached yet (scripts/download_models.py does it)
        if local_only:
            raise
        model = SentenceTransformer(model_name, device="cpu")
    return Embedder(model, query_prefix=query_prefix_for(model_name))


_cache: dict[str, Embedder] = {}
_lock = threading.Lock()


def get_embedder(model_name: str) -> Embedder:
    """One model per process. The lock only guards *loading* (so two threads never load it
    twice); encoding runs without it."""
    with _lock:
        if model_name not in _cache:
            _cache[model_name] = load_embedder(model_name)
        return _cache[model_name]
