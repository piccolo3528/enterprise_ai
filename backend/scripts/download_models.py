"""Download the local embedding + reranker models and smoke-test them on CPU.

Run once from backend/ with the venv active:
    python scripts/download_models.py

Models are cached by Hugging Face under %USERPROFILE%\\.cache\\huggingface, so the app
(and verify_setup.py) can later load them without network access.

The smoke test is also a first look at the concepts we'll build on in M9 and M14:
  * an embedding turns text into a fixed-length vector (384 numbers for bge-small)
  * normalized vectors have length 1, so cosine similarity == dot product
  * a related sentence scores higher than an unrelated one
  * BGE expects an instruction prefix on QUERIES only (asymmetric retrieval)
  * a cross-encoder reads (query, passage) together and outputs a relevance score
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from dotenv import dotenv_values

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV = dotenv_values(BACKEND_DIR / ".env")
EMBEDDING_MODEL = ENV.get("EMBEDDING_MODEL") or "BAAI/bge-small-en-v1.5"
RERANKER_MODEL = ENV.get("RERANKER_MODEL") or "cross-encoder/ms-marco-MiniLM-L-6-v2"

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

QUERY = "How many days of unused leave can be carried forward?"
RELEVANT = (
    "Employees may carry forward up to 10 days of unused annual leave into the next leave year."
)
UNRELATED = "Expense claims must be submitted within 30 days of the expense."


def main() -> int:
    from sentence_transformers import CrossEncoder, SentenceTransformer

    print(f"Embedding model: {EMBEDDING_MODEL}")
    t0 = time.perf_counter()
    embedder = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    print(
        f"  loaded in {time.perf_counter() - t0:.1f}s "
        f"| dimension {embedder.get_embedding_dimension()} "
        f"| max tokens per input {embedder.max_seq_length}"
    )

    query_vec = embedder.encode([BGE_QUERY_PREFIX + QUERY], normalize_embeddings=True)[0]
    passages = embedder.encode([RELEVANT, UNRELATED], normalize_embeddings=True)

    # Cosine similarity by hand: a.b / (|a| |b|). With normalized vectors |a| = |b| = 1.
    norms = np.linalg.norm(passages, axis=1)
    cosine = passages @ query_vec / (norms * np.linalg.norm(query_vec))
    dot = passages @ query_vec
    print(f"  vector length after normalization: {norms.round(4).tolist()}")
    print(f"  cosine(query, relevant)  = {cosine[0]:.3f}")
    print(f"  cosine(query, unrelated) = {cosine[1]:.3f}")
    print(f"  cosine == dot product for normalized vectors: {np.allclose(cosine, dot)}")
    if not cosine[0] > cosine[1]:
        print("  FAIL: relevant passage should score higher")
        return 1

    print(f"\nReranker model: {RERANKER_MODEL}")
    t0 = time.perf_counter()
    reranker = CrossEncoder(RERANKER_MODEL, device="cpu")
    print(f"  loaded in {time.perf_counter() - t0:.1f}s")
    scores = reranker.predict([(QUERY, RELEVANT), (QUERY, UNRELATED)])
    print(f"  score(query, relevant)  = {scores[0]:.2f}")
    print(f"  score(query, unrelated) = {scores[1]:.2f}")
    print("  (raw logits: higher = more relevant; we'll squash them with a sigmoid in M14)")
    if not scores[0] > scores[1]:
        print("  FAIL: relevant passage should score higher")
        return 1

    print("\nPASS: both models downloaded, cached and working on CPU.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
