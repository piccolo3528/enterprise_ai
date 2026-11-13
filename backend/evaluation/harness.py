"""The evaluation harness: index the corpus with a chunking config, ask every labelled question
through the app's real search code, and record what came back.

Nothing is kept anywhere:
- PostgreSQL: the Neon **test** branch, inside ONE transaction that is never committed. The
  searches run in the same session, so they see the uncommitted rows; nobody else ever does.
- Qdrant: a throwaway collection (`chunks_eval`), deleted at the end.
So the evaluation measures `retrieval.search` exactly as the API runs it (PostgreSQL full-text
search, Qdrant, the confirmation join, RRF), without touching the user's data.

Relevance comes from character offsets, not labels: each chunk's body span is compared with the
body of every section, so a chunk counts for "§4.1" only if it contains some of §4.1's text
(a heading line trailing at the end of a chunk doesn't count).
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import re
import time
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import build_engine
from app.models import Chunk, Document, KnowledgeBase, User
from app.services import retrieval
from app.services.embeddings import Embedder
from app.services.ingestion.base import Block
from app.services.ingestion.chunking import Assembled, assemble, chunk_document
from app.services.ingestion.extractors import extract
from app.services.ingestion.pipeline import chunk_rows, point_payload
from app.services.ingestion.tokens import TokenCounter
from app.services.vector_store import ChunkPoint, VectorStore, build_qdrant_client

EVAL_DIR = Path(__file__).resolve().parent
CORPUS_DIR = EVAL_DIR / "corpus"
DATASET = EVAL_DIR / "datasets" / "eval_dataset.json"
REPORTS_DIR = EVAL_DIR / "reports"
EVAL_COLLECTION = "chunks_eval"

# "4.1 Annual entitlement" -> "4.1"; "4. Entitlements" -> "4"; "Document Control" -> no number
_SECTION_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)\.?(?=\s|$)")


# --- the labelled questions ----------------------------------------------------------------------


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    type: str
    answerable: bool
    relevant: frozenset[str]  # "NX-HR-002 v3.0 §4.1", ...
    expected_documents: frozenset[str]  # "NX-HR-002", ...
    expected_versions: frozenset[str]  # "NX-HR-002 v3.0", ...


def load_questions(path: Path = DATASET) -> list[Question]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        Question(
            id=q["question_id"],
            text=q["question"],
            type=q["question_type"],
            answerable=q["answerable"],
            relevant=frozenset(q["expected_sections"]),
            expected_documents=frozenset(q["expected_document_ids"]),
            expected_versions=frozenset(q["expected_versions"]),
        )
        for q in data["questions"]
    ]


# --- which sections a chunk covers ---------------------------------------------------------------


def section_number(headings: Sequence[str]) -> str | None:
    """The number of the deepest numbered heading: ("Policy", "4. Leave", "4.1 Annual") -> "4.1"."""
    for heading in reversed(headings):
        match = _SECTION_NUMBER.match(heading.strip())
        if match:
            return match.group(1)
    return None


def covered_units(
    blocks: Sequence[Block], assembled: Assembled, start: int, end: int, label: str
) -> frozenset[str]:
    """The sections whose *body text* overlaps the span [start, end) of the assembled text.

    `assemble` writes one segment per block: the headings that are new at that block, then the
    block's text. So the body starts at `segment.end - len(block.text)`.
    """
    units = set()
    for block, segment in zip(blocks, assembled.segments, strict=True):
        body_start = segment.end - len(block.text)
        if body_start < end and start < segment.end:
            number = section_number(segment.headings)
            if number:
                units.add(f"{label} §{number}")
    return frozenset(units)


# --- building the index --------------------------------------------------------------------------


@dataclass(frozen=True)
class ChunkingConfig:
    strategy: str  # heading | recursive | fixed | overlap
    size: int = 400
    overlap: int = 60
    # Heading-aware chunks start with a context header ("NX-HR-002 v3.0 · 4. Entitlements › ...").
    # False = embed and search the same chunks without it (an experiment; the app always adds it).
    header: bool = True

    @property
    def name(self) -> str:
        overlap = f"/{self.overlap}" if self.strategy in ("overlap", "recursive", "heading") else ""
        no_header = " no-header" if self.strategy == "heading" and not self.header else ""
        return f"{self.strategy} {self.size}{overlap}{no_header}"


@dataclass
class Index:
    config: ChunkingConfig
    owner_id: uuid.UUID
    kb_id: uuid.UUID
    units: dict[uuid.UUID, frozenset[str]] = field(default_factory=dict)
    tokens: dict[uuid.UUID, int] = field(default_factory=dict)
    version_of: dict[uuid.UUID, str] = field(default_factory=dict)  # chunk -> "NX-HR-002 v3.0"
    documents: int = 0
    # How many vectors Qdrant has put into its HNSW graph. 0 = every search compares against
    # all vectors (exact): small collections stay below Qdrant's indexing threshold.
    hnsw_indexed: int | None = None
    seconds: dict[str, float] = field(default_factory=dict)

    @property
    def chunk_count(self) -> int:
        return len(self.units)


def build_index(
    db: Session,
    vectors: VectorStore,
    embedder: Embedder,
    tokens: TokenCounter,
    config: ChunkingConfig,
    corpus_dir: Path = CORPUS_DIR,
) -> Index:
    """Chunk, store (uncommitted) and embed every corpus document into a fresh collection."""
    started = time.perf_counter()
    owner = User(email=f"eval-{uuid.uuid4().hex[:12]}@example.invalid", password_hash="x",
                 full_name="Evaluation")  # fmt: skip
    db.add(owner)
    db.flush()
    kb = KnowledgeBase(owner_id=owner.id, name=f"Evaluation corpus ({config.name})")
    db.add(kb)
    db.flush()
    index = Index(config=config, owner_id=owner.id, kb_id=kb.id)

    all_rows: list[dict] = []
    metadata_of: dict[uuid.UUID, dict] = {}
    for path in sorted(corpus_dir.rglob("*.md")):
        extraction = extract(path, "md")
        meta = extraction.metadata
        label = f"{meta['document_id']} v{meta['version']}"
        drafts = chunk_document(
            extraction.blocks, meta, tokens,
            strategy=config.strategy, size=config.size, overlap=config.overlap,
        )  # fmt: skip
        assembled = assemble(extraction.blocks)
        data = path.read_bytes()
        document = Document(
            id=uuid.uuid4(),
            kb_id=kb.id,
            original_filename=path.name,
            stored_path=f"evaluation/{path.name}",
            file_type="md",
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            status="ready",
            doc_metadata=meta,
            chunk_count=len(drafts),
            processed_at=datetime.now(UTC),
        )
        db.add(document)
        rows = chunk_rows(drafts, document.id, kb.id)
        for row, draft in zip(rows, drafts, strict=True):
            if not config.header:
                row["text"] = assembled.text[draft.start : draft.end]
                row["token_count"] = tokens.count(row["text"])
            index.units[row["id"]] = covered_units(
                extraction.blocks, assembled, draft.start, draft.end, label
            )
            index.tokens[row["id"]] = row["token_count"]
            index.version_of[row["id"]] = label
            metadata_of[row["id"]] = meta
        all_rows.extend(rows)
        index.documents += 1
    db.flush()
    db.execute(insert(Chunk), all_rows)
    index.seconds["chunk+store"] = time.perf_counter() - started

    t = time.perf_counter()
    embedded = embedder.embed_documents([row["text"] for row in all_rows])
    index.seconds["embed"] = time.perf_counter() - t

    t = time.perf_counter()
    vectors.recreate(embedder.dimension)
    vectors.upsert(
        [
            ChunkPoint(row["id"], vector, point_payload(row, owner.id, metadata_of[row["id"]]))
            for row, vector in zip(all_rows, embedded, strict=True)
        ]
    )
    index.seconds["index"] = time.perf_counter() - t
    index.hnsw_indexed = vectors.client.get_collection(vectors.collection).indexed_vectors_count
    return index


# --- asking the questions ------------------------------------------------------------------------


@dataclass(frozen=True)
class Variant:
    mode: str  # semantic | keyword | hybrid
    prefix: bool = True  # BGE query prefix on (semantic side only)

    @property
    def name(self) -> str:
        if self.mode == "keyword":
            return "keyword"
        return self.mode if self.prefix else f"{self.mode} (no prefix)"


@dataclass(frozen=True)
class Hit:
    chunk_id: uuid.UUID
    score: float
    units: frozenset[str]
    version: str  # "NX-HR-002 v3.0"
    tokens: int
    semantic_score: float | None


@dataclass
class Answer:
    question: Question
    variant: Variant
    hits: list[Hit]
    timings_ms: dict[str, float]


def ask_all(
    db: Session,
    vectors: VectorStore,
    embedder: Embedder,
    index: Index,
    questions: Sequence[Question],
    variant: Variant,
    *,
    top_k: int = 10,
    candidates: int = 20,
) -> list[Answer]:
    """Every question through `retrieval.search`, exactly as the API calls it."""
    model = embedder
    if not variant.prefix:
        model = copy.copy(embedder)
        model.query_prefix = ""
    answers = []
    for question in questions:
        outcome = retrieval.search(
            db, vectors, lambda: model,
            owner_id=index.owner_id, kb_id=index.kb_id, query=question.text,
            mode=variant.mode, top_k=top_k, candidates=candidates,
        )  # fmt: skip
        hits = [
            Hit(
                chunk_id=r.passage.chunk_id,
                score=r.score,
                units=index.units[r.passage.chunk_id],
                version=index.version_of[r.passage.chunk_id],
                tokens=index.tokens[r.passage.chunk_id],
                semantic_score=r.semantic_score,
            )
            for r in outcome.results
        ]
        answers.append(Answer(question, variant, hits, outcome.timings_ms))
    return answers


# --- the throwaway environment -------------------------------------------------------------------


@contextlib.contextmanager
def evaluation_session(settings: Settings) -> Iterator[tuple[Session, VectorStore]]:
    """A session on the Neon test branch whose work is always rolled back, and a throwaway
    Qdrant collection that is deleted afterwards. Refuses to run against the dev database or
    the app's own collections."""
    if settings.test_database_url is None:
        raise SystemExit(
            "TEST_DATABASE_URL is not set: the evaluation runs on the Neon test branch"
        )
    test_url = settings.test_database_url.get_secret_value()
    if urlsplit(test_url).hostname == urlsplit(settings.database_url.get_secret_value()).hostname:
        raise SystemExit("TEST_DATABASE_URL points at the development database; refusing to run")
    if EVAL_COLLECTION in (settings.qdrant_collection, "chunks_test"):
        raise SystemExit(f"'{EVAL_COLLECTION}' is in use by the app or the tests; refusing to run")

    engine = build_engine(test_url)
    client = build_qdrant_client(settings)
    vectors = VectorStore(client, EVAL_COLLECTION)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            db = Session(bind=connection, join_transaction_mode="create_savepoint")
            try:
                yield db, vectors
            finally:
                db.close()
                transaction.rollback()  # nothing the evaluation wrote survives
    finally:
        client.delete_collection(EVAL_COLLECTION)
        client.close()
        engine.dispose()
