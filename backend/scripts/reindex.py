"""Rebuild the Qdrant collection from the chunks in PostgreSQL, or check that the two agree.

PostgreSQL is the system of record: it holds every chunk's text, so every vector can be
recomputed. That makes Qdrant disposable. Use this when the collection was lost (Qdrant Cloud
deletes free clusters after 4 weeks of inactivity), after changing EMBEDDING_MODEL, or to clear
orphan points.

Usage (backend/ folder, venv active):
    python scripts/reindex.py --check   # compare only: points per document vs chunks (no changes)
    python scripts/reindex.py           # drop + recreate the collection, re-embed every chunk of
                                        # every ready document, then run the check

Run the rebuild while no upload is processing: a job that indexes during the rebuild can be
wiped by it (the check at the end would report that document). Prints ids, names and counts only.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `app` importable

from sqlalchemy import func, select  # noqa: E402

from app.core.config import load_settings  # noqa: E402
from app.db.session import build_engine, build_session_factory  # noqa: E402
from app.models import Chunk, Document, KnowledgeBase  # noqa: E402
from app.services.embeddings import get_embedder  # noqa: E402
from app.services.ingestion.pipeline import point_payload  # noqa: E402
from app.services.vector_store import ChunkPoint, VectorStore, build_qdrant_client  # noqa: E402


def check(session_factory, vectors: VectorStore) -> bool:
    """Points per document in Qdrant == chunk rows per ready document in PostgreSQL, and no
    points for anything else."""
    with session_factory() as db:
        rows = db.execute(
            select(Document.id, Document.original_filename, func.count(Chunk.id))
            .join(Chunk, Chunk.document_id == Document.id, isouter=True)
            .where(Document.status == "ready")
            .group_by(Document.id, Document.original_filename)
        ).all()
    expected = {str(doc_id): (name, count) for doc_id, name, count in rows}
    actual = vectors.points_per_document()

    mismatched = [
        (name, count, actual.get(doc_id, 0))
        for doc_id, (name, count) in expected.items()
        if actual.get(doc_id, 0) != count
    ]
    orphans = {doc_id: n for doc_id, n in actual.items() if doc_id not in expected}
    chunks = sum(count for _, count in expected.values())
    print(
        f"PostgreSQL: {len(expected)} ready documents, {chunks} chunks | "
        f"Qdrant '{vectors.collection}': {sum(actual.values())} points"
    )
    for name, count, points in mismatched:
        print(f"  MISMATCH {name}: {count} chunks, {points} points")
    for doc_id, n in orphans.items():
        print(f"  ORPHAN   {n} points for document {doc_id} (not ready or deleted)")
    ok = not mismatched and not orphans
    print("OK: every ready chunk has exactly one point." if ok else "Differences found.")
    return ok


def rebuild(session_factory, vectors: VectorStore, model_name: str) -> None:
    started = time.perf_counter()
    embedder = get_embedder(model_name)
    print(f"Embedding model loaded in {time.perf_counter() - started:.1f} s ({model_name})")
    vectors.recreate(embedder.dimension)
    print(f"Collection '{vectors.collection}' recreated ({embedder.dimension}-d, cosine)")

    with session_factory() as db:
        documents = db.execute(
            select(
                Document.id,
                Document.original_filename,
                Document.doc_metadata,
                KnowledgeBase.owner_id,
            )
            .join(KnowledgeBase, KnowledgeBase.id == Document.kb_id)
            .where(Document.status == "ready")
            .order_by(Document.created_at)
        ).all()

    total = 0
    for doc in documents:
        doc_started = time.perf_counter()
        with session_factory() as db:  # short read; no connection held while embedding
            chunks = list(
                db.scalars(
                    select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.chunk_index)
                )
            )
        embedded = embedder.embed_documents([c.text for c in chunks])
        vectors.upsert(
            [
                ChunkPoint(c.id, vector, point_payload(c, doc.owner_id, doc.doc_metadata))
                for c, vector in zip(chunks, embedded, strict=True)
            ]
        )
        total += len(chunks)
        print(
            f"  {len(chunks):4} chunks  {time.perf_counter() - doc_started:5.1f} s  "
            f"{doc.original_filename}"
        )
    elapsed = time.perf_counter() - started
    print(f"Indexed {total} chunks of {len(documents)} documents in {elapsed:.1f} s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="compare only; change nothing")
    args = parser.parse_args()

    settings = load_settings()
    engine = build_engine(settings.database_url.get_secret_value())
    session_factory = build_session_factory(engine)
    qdrant = build_qdrant_client(settings)
    vectors = VectorStore(qdrant, settings.qdrant_collection)
    try:
        if not args.check:
            rebuild(session_factory, vectors, settings.embedding_model)
        return 0 if check(session_factory, vectors) else 1
    finally:
        qdrant.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
