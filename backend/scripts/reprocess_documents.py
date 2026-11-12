"""Re-run extraction, chunking and embedding for existing documents, without the web server.

When to use it:
- documents uploaded before M8 are "ready" but have no chunks (tracker L33);
- after changing CHUNK_STRATEGY / CHUNK_SIZE_TOKENS / CHUNK_OVERLAP_TOKENS in backend/.env, so
  every document is chunked the same way (M11 compares strategies this way).

Usage (backend/ folder, venv active):
    python scripts/reprocess_documents.py              # ready documents with 0 chunks (default)
    python scripts/reprocess_documents.py --all        # every ready or failed document
    python scripts/reprocess_documents.py --dry-run    # list what would be processed

It uses the same job as the server (app/services/ingestion/pipeline.py), so the result is
identical. Prints ids, names and counts only; no settings or secrets.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `app` importable

from sqlalchemy import select, update  # noqa: E402

from app.core.config import load_settings  # noqa: E402
from app.db.session import build_engine, build_session_factory  # noqa: E402
from app.models import Document  # noqa: E402
from app.services.ingestion.pipeline import IngestionConfig, process_document  # noqa: E402
from app.services.storage import Storage  # noqa: E402
from app.services.vector_store import VectorStore, build_qdrant_client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--all", action="store_true", help="every ready or failed document")
    parser.add_argument("--dry-run", action="store_true", help="only list the documents")
    args = parser.parse_args()

    settings = load_settings()
    engine = build_engine(settings.database_url.get_secret_value())
    session_factory = build_session_factory(engine)
    storage = Storage(settings.upload_dir)
    config = IngestionConfig.from_settings(settings)
    qdrant = build_qdrant_client(settings)
    vectors = VectorStore(qdrant, settings.qdrant_collection)

    try:
        with session_factory() as db:
            query = select(Document.id, Document.original_filename, Document.status)
            if args.all:
                query = query.where(Document.status.in_(("ready", "failed")))
            else:
                query = query.where(Document.status == "ready", Document.chunk_count == 0)
            targets = db.execute(query.order_by(Document.created_at)).all()

        print(
            f"{len(targets)} document(s) to process (strategy={config.strategy}, "
            f"size={config.size}, overlap={config.overlap})"
        )
        for target in targets:
            print(f"  {target.id}  {target.status:7}  {target.original_filename}")
        if args.dry_run or not targets:
            return 0

        started = time.perf_counter()
        for target in targets:
            with session_factory() as db:
                # Same transition as the reprocess endpoint: only from ready/failed.
                queued = db.execute(
                    update(Document)
                    .where(Document.id == target.id, Document.status.in_(("ready", "failed")))
                    .values(status="uploaded", error_message=None)
                ).rowcount
                db.commit()
            if not queued:
                print(f"  skipped {target.id} (it changed meanwhile)")
                continue
            process_document(session_factory, storage, vectors, config, target.id)

        with session_factory() as db:
            done = db.execute(
                select(Document.original_filename, Document.status, Document.chunk_count).where(
                    Document.id.in_([t.id for t in targets])
                )
            ).all()
        for row in done:
            print(f"  {row.status:7} {row.chunk_count:4} chunks  {row.original_filename}")
        print(f"Done in {time.perf_counter() - started:.1f} s")
        return 0 if all(row.status == "ready" for row in done) else 1
    finally:
        qdrant.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
