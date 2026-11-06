"""Milestone 1: verify every external dependency works from this machine.

Run from backend/ with the venv active:
    python scripts/verify_setup.py            # all checks
    python scripts/verify_setup.py --skip-llm # don't spend Gemini quota

Checks (each prints PASS / FAIL / WARN with timings):
  1. Neon pooled connection (the app's URL): TLS, server version, round-trip latency
  2. Neon direct connection (Alembic's URL)
  3. PostgreSQL full-text search on Neon: generated tsvector column, GIN index,
     websearch_to_tsquery, ts_rank_cd (inside a transaction that is rolled back)
  4. Optional hardening: sslmode=verify-full against the system CA store
  5. Qdrant: create collection, payload index, upsert, filtered search, delete
  6. Gemini: one small generate call + one streaming call
  7. Local models load from the Hugging Face cache (run download_models.py first)
  8. Optional: Groq key lists models (no generation)

Secrets are never printed: error messages are passed through redact().
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import dotenv_values

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV = {k: (v or "").strip() for k, v in dotenv_values(BACKEND_DIR / ".env").items()}

RESULTS: list[tuple[str, str, str]] = []  # (status, name, detail)


# --------------------------------------------------------------------------- helpers
def _secrets() -> list[str]:
    values = [
        ENV.get(k, "") for k in ("GEMINI_API_KEY", "QDRANT_API_KEY", "GROQ_API_KEY", "JWT_SECRET")
    ]
    for k in ("DATABASE_URL", "DATABASE_MIGRATION_URL", "TEST_DATABASE_URL"):
        password = urlsplit(ENV.get(k, "")).password
        values.append(password or "")
    return [v for v in values if len(v) >= 6]


def redact(message: str) -> str:
    for secret in _secrets():
        message = message.replace(secret, "***")
    return message


def record(status: str, name: str, detail: str = "") -> None:
    RESULTS.append((status, name, detail))
    print(f"[{status}] {name}" + (f" -- {detail}" if detail else ""), flush=True)


def check(name: str, fn: Callable[[], str], *, optional: bool = False) -> None:
    """Run one check; exceptions become FAIL (or WARN for optional checks)."""
    try:
        record("PASS", name, fn())
    except Exception as exc:  # noqa: BLE001 - we want every failure reported, not raised
        detail = redact(f"{type(exc).__name__}: {exc}").splitlines()[0][:300]
        record("WARN" if optional else "FAIL", name, detail)


def ms(seconds: float) -> str:
    return f"{seconds * 1000:.0f} ms"


# --------------------------------------------------------------------------- Neon
def make_engine(url: str):
    """Engine configured the way the app will configure it (ARCHITECTURE section 4.12)."""
    from sqlalchemy import create_engine

    return create_engine(
        url,
        pool_pre_ping=True,  # replace connections killed by Neon's scale-to-zero
        pool_recycle=240,  # retire connections before the 5-minute idle suspend
        connect_args={
            # Measured from India -> us-east-1: ~1.4-1.6 s per new TLS connection, more if the
            # compute is waking from scale-to-zero. 10 s was too tight on a cold start.
            "connect_timeout": 30,
            "prepare_threshold": None,  # no auto-prepared statements behind PgBouncer
            "sslnegotiation": "direct",  # TLS immediately, skipping one round trip (libpq >= 17)
        },
    )


def check_neon(env_key: str) -> str:
    from sqlalchemy import text

    url = ENV.get(env_key, "")
    if not url or "USER:PASSWORD" in url:
        raise RuntimeError(f"{env_key} is not set in backend/.env")
    engine = make_engine(url)
    try:
        t0 = time.perf_counter()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            first = time.perf_counter() - t0  # TCP + TLS + auth (+ compute wake-up if asleep)

            t1 = time.perf_counter()
            for _ in range(3):
                conn.execute(text("SELECT 1"))
            round_trip = (time.perf_counter() - t1) / 3  # pure network round trip

            version = conn.execute(text("SHOW server_version")).scalar()
            ssl_in_use = conn.connection.driver_connection.pgconn.ssl_in_use
        if not ssl_in_use:
            raise RuntimeError("connection is NOT using TLS")
        return (
            f"PostgreSQL {version}, TLS on, first query {ms(first)} "
            f"(connect+TLS, maybe wake-up), warm round trip {ms(round_trip)}"
        )
    finally:
        engine.dispose()


FTS_DOCS = [
    (1, "Employees may carry forward up to 10 days of unused annual leave into the next year."),
    (2, "Hybrid work requires a minimum of three office days per week; Tuesday is an anchor day."),
    (3, "Expense claims must be submitted in NexClaim within 30 days of the expense."),
]


def check_full_text_search() -> str:
    """Exercise exactly the FTS features the hybrid retriever will rely on, then roll back."""
    from sqlalchemy import text

    engine = make_engine(ENV["DATABASE_MIGRATION_URL"])
    try:
        with engine.connect() as conn:
            trans = conn.begin()  # PostgreSQL DDL is transactional: rollback leaves no trace
            try:
                conn.execute(
                    text("""
                    CREATE TABLE fts_check (
                        id   int PRIMARY KEY,
                        body text NOT NULL,
                        search_vector tsvector
                            GENERATED ALWAYS AS (to_tsvector('english', body)) STORED
                    )""")
                )
                conn.execute(
                    text("CREATE INDEX fts_check_gin ON fts_check USING gin (search_vector)")
                )
                conn.execute(
                    text("INSERT INTO fts_check (id, body) VALUES (:id, :body)"),
                    [{"id": i, "body": b} for i, b in FTS_DOCS],
                )

                search = text("""
                    SELECT id, ts_rank_cd(search_vector, q) AS rank
                    FROM fts_check, websearch_to_tsquery('english', :q) AS q
                    WHERE search_vector @@ q
                    ORDER BY rank DESC""")

                # Stemming: "carried"/"leaves" must match "carry"/"leave".
                hits = conn.execute(search, {"q": "carried forward leaves"}).all()
                assert [h.id for h in hits] == [1], f"stemming query returned {hits}"
                # websearch syntax: quoted phrase + exclusion.
                hits = conn.execute(search, {"q": '"office days" -expense'}).all()
                assert [h.id for h in hits] == [2], f"phrase/exclusion query returned {hits}"
                # Nonsense must return nothing (no false positives).
                hits = conn.execute(search, {"q": "pet policy sabbatical"}).all()
                assert hits == [], f"irrelevant query returned {hits}"

                # The GIN index must be usable by the planner.
                conn.execute(text("SET LOCAL enable_seqscan = off"))
                plan = "\n".join(
                    r[0]
                    for r in conn.execute(
                        text(
                            "EXPLAIN SELECT id FROM fts_check "
                            "WHERE search_vector @@ websearch_to_tsquery('english', 'leave')"
                        )
                    )
                )
                assert "fts_check_gin" in plan, f"GIN index not used:\n{plan}"
            finally:
                trans.rollback()
        return (
            "generated tsvector, GIN index (used by planner), websearch_to_tsquery "
            "(stemming, phrase, exclusion), ts_rank_cd all OK; rolled back"
        )
    finally:
        engine.dispose()


def check_verify_full() -> str:
    """Stricter TLS: verify Neon's certificate chain and hostname, not just encrypt.

    sslrootcert=system fails on Windows (libpq's OpenSSL doesn't read the Windows cert
    store), so we point libpq at certifi's Mozilla CA bundle instead.
    """
    import certifi
    from sqlalchemy import text

    parts = urlsplit(ENV["DATABASE_URL"])
    query = dict(parse_qsl(parts.query))
    query.update({"sslmode": "verify-full", "sslrootcert": certifi.where()})
    engine = make_engine(urlunsplit(parts._replace(query=urlencode(query))))
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "certificate chain + hostname verified with certifi CA bundle"
    finally:
        engine.dispose()


# --------------------------------------------------------------------------- Qdrant
def check_qdrant() -> str:
    from qdrant_client import QdrantClient, models

    client = QdrantClient(
        url=ENV["QDRANT_URL"], api_key=ENV.get("QDRANT_API_KEY") or None, timeout=30
    )
    name = f"verify_setup_{uuid.uuid4().hex[:8]}"  # throwaway collection, deleted below
    t0 = time.perf_counter()
    try:
        client.create_collection(
            name, vectors_config=models.VectorParams(size=4, distance=models.Distance.COSINE)
        )
        client.create_payload_index(
            name, field_name="kb_id", field_schema=models.PayloadSchemaType.KEYWORD
        )
        client.upsert(
            name,
            points=[
                models.PointStruct(id=1, vector=[1.0, 0.0, 0.0, 0.0], payload={"kb_id": "kb-a"}),
                models.PointStruct(id=2, vector=[0.9, 0.1, 0.0, 0.0], payload={"kb_id": "kb-b"}),
                models.PointStruct(id=3, vector=[0.0, 1.0, 0.0, 0.0], payload={"kb_id": "kb-a"}),
            ],
            wait=True,
        )
        t_search = time.perf_counter()
        hits = client.query_points(
            name,
            query=[1.0, 0.05, 0.0, 0.0],
            query_filter=models.Filter(
                must=[models.FieldCondition(key="kb_id", match=models.MatchValue(value="kb-a"))]
            ),
            limit=3,
        ).points
        search_time = time.perf_counter() - t_search
        # Point 2 is the nearest overall but belongs to kb-b, so the filter must exclude it.
        assert [h.id for h in hits] == [1, 3], f"unexpected filtered results {[h.id for h in hits]}"
        return (
            f"create/index/upsert/filtered search OK (tenant filter excluded the nearer kb-b "
            f"point); search {ms(search_time)}, total {ms(time.perf_counter() - t0)}"
        )
    finally:
        if client.collection_exists(name):
            client.delete_collection(name)
        client.close()


# --------------------------------------------------------------------------- Gemini
def _gemini():
    from google import genai
    from google.genai import types

    key = ENV.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    config = types.GenerateContentConfig(temperature=0.0, max_output_tokens=256)
    return (
        genai.Client(api_key=key),
        ENV.get("GEMINI_MODEL_ANSWER") or "gemini-3.5-flash-lite",
        config,
    )


def check_gemini_generate() -> str:
    client, model, config = _gemini()
    t0 = time.perf_counter()
    resp = client.models.generate_content(
        model=model, contents="Reply with exactly the word: READY", config=config
    )
    elapsed = time.perf_counter() - t0
    answer = (resp.text or "").strip()
    usage = resp.usage_metadata
    assert "READY" in answer.upper(), f"unexpected reply {answer!r}"
    return (
        f"{model} replied {answer!r} in {ms(elapsed)} "
        f"(prompt {usage.prompt_token_count} tokens, output {usage.candidates_token_count} tokens)"
    )


def check_gemini_stream() -> str:
    client, model, config = _gemini()
    t0 = time.perf_counter()
    first_chunk_at = None
    pieces = []
    for chunk in client.models.generate_content_stream(
        model=model, contents="Count from 1 to 5, separated by spaces.", config=config
    ):
        if chunk.text:
            first_chunk_at = first_chunk_at or time.perf_counter() - t0
            pieces.append(chunk.text)
    text_out = "".join(pieces).strip()
    assert "5" in text_out, f"unexpected stream {text_out!r}"
    return (
        f"{len(pieces)} chunk(s), first token after {ms(first_chunk_at or 0)}, "
        f"total {ms(time.perf_counter() - t0)}: {text_out!r}"
    )


# --------------------------------------------------------------------------- local models
def check_models_cached() -> str:
    os.environ["HF_HUB_OFFLINE"] = "1"  # prove the models load WITHOUT network access
    os.environ["HF_HUB_VERBOSITY"] = "error"  # hide "offline mode" notices
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["TRANSFORMERS_VERBOSITY"] = "error"
    from sentence_transformers import CrossEncoder, SentenceTransformer

    embedder = SentenceTransformer(ENV["EMBEDDING_MODEL"], device="cpu")
    vec = embedder.encode(["test"], normalize_embeddings=True)
    reranker = CrossEncoder(ENV["RERANKER_MODEL"], device="cpu")
    reranker.predict([("query", "passage")])
    return f"{ENV['EMBEDDING_MODEL']} (dim {vec.shape[1]}) and {ENV['RERANKER_MODEL']} load offline"


# --------------------------------------------------------------------------- Groq
def check_groq() -> str:
    key = ENV.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not set (optional)")
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {key}", "User-Agent": "eki-verify-setup"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            ids = sorted(m["id"] for m in json.load(r)["data"])
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}") from None
    return f"key accepted; {len(ids)} models, e.g. {', '.join(ids[:6])}"


# --------------------------------------------------------------------------- main
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--skip-llm", action="store_true", help="skip the Gemini calls (saves quota)"
    )
    args = parser.parse_args()

    if not (BACKEND_DIR / ".env").exists():
        print("backend/.env not found. Copy .env.example to .env and fill it in.")
        return 2

    print("== Neon PostgreSQL ==")
    check("Neon pooled connection (DATABASE_URL)", lambda: check_neon("DATABASE_URL"))
    check(
        "Neon direct connection (DATABASE_MIGRATION_URL)",
        lambda: check_neon("DATABASE_MIGRATION_URL"),
    )
    check("PostgreSQL full-text search on Neon", check_full_text_search)
    check("TLS verify-full (optional hardening)", check_verify_full, optional=True)

    print("== Qdrant ==")
    check("Qdrant collection lifecycle + filtered search", check_qdrant)

    print("== Gemini ==")
    if args.skip_llm:
        record("WARN", "Gemini checks", "skipped (--skip-llm)")
    else:
        check("Gemini generate", check_gemini_generate)
        check("Gemini streaming", check_gemini_stream)

    print("== Local models ==")
    check("Embedding + reranker models (offline load)", check_models_cached)

    print("== Optional ==")
    check("Groq API key (list models)", check_groq, optional=True)

    failed = [r for r in RESULTS if r[0] == "FAIL"]
    warned = [r for r in RESULTS if r[0] == "WARN"]
    print(
        f"\nSummary: {len(RESULTS) - len(failed) - len(warned)} passed, "
        f"{len(warned)} warnings, {len(failed)} failed"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
