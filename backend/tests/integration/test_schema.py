"""Database rules enforced by PostgreSQL itself. Runs on the Neon test branch, rolled back."""

from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.db.session import build_read_session_factory
from app.models import Chunk, Conversation, Document, KnowledgeBase, Message, User

pytestmark = pytest.mark.live


def make_user(db, email=None) -> User:
    user = User(
        email=email or f"user-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        full_name="Test User",
    )
    db.add(user)
    db.flush()
    return user


def make_kb(db, owner, name="Policies") -> KnowledgeBase:
    kb = KnowledgeBase(owner_id=owner.id, name=name)
    db.add(kb)
    db.flush()
    return kb


def make_document(db, kb, content=b"hello", **overrides) -> Document:
    doc = Document(
        kb_id=kb.id,
        original_filename="policy.md",
        stored_path=f"{kb.id}/{uuid.uuid4()}.md",
        file_type="md",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        **overrides,
    )
    db.add(doc)
    db.flush()
    return doc


def expect_rejected(db, constraint_name):
    """Flush and assert PostgreSQL rejected it because of this exact constraint."""
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    db.rollback()
    assert constraint_name in str(exc_info.value.orig)


def test_server_defaults_come_back_with_the_insert(db):
    doc = make_document(db, make_kb(db, make_user(db)))
    assert doc.status == "uploaded"
    assert doc.doc_metadata == {}
    assert doc.chunk_count == 0
    assert doc.created_at is not None


def test_email_is_unique(db):
    make_user(db, "same@example.com")
    db.add(User(email="same@example.com", password_hash="x", full_name="Copy"))
    expect_rejected(db, "uq_users_email")


def test_email_must_be_lowercase(db):
    db.add(User(email="Mixed@Example.com", password_hash="x", full_name="M"))
    expect_rejected(db, "ck_users_email_lowercase")


def test_knowledge_base_names_are_unique_per_owner(db):
    alice, bob = make_user(db), make_user(db)
    make_kb(db, alice, "HR")
    make_kb(db, bob, "HR")  # another owner may reuse the name
    db.add(KnowledgeBase(owner_id=alice.id, name="hr"))  # same name, different case (M6)
    expect_rejected(db, "uq_knowledge_bases_owner_id_lower_name")


def test_document_status_must_be_known(db):
    kb = make_kb(db, make_user(db))
    db.add(
        Document(
            kb_id=kb.id,
            original_filename="x.md",
            stored_path="x",
            file_type="md",
            size_bytes=1,
            sha256="0" * 64,
            status="done",
        )
    )
    expect_rejected(db, "ck_documents_status")


def test_same_file_twice_in_one_kb_is_rejected_but_allowed_in_another(db):
    owner = make_user(db)
    kb1, kb2 = make_kb(db, owner, "A"), make_kb(db, owner, "B")
    make_document(db, kb1, b"same bytes")
    make_document(db, kb2, b"same bytes")  # different knowledge base: fine
    db.add(
        Document(
            kb_id=kb1.id,
            original_filename="copy.md",
            stored_path="y",
            file_type="md",
            size_bytes=10,
            sha256=hashlib.sha256(b"same bytes").hexdigest(),
        )
    )
    expect_rejected(db, "uq_documents_kb_id_sha256")


def test_deleting_a_user_cascades_to_everything_they_own(db):
    user = make_user(db)
    kb = make_kb(db, user)
    doc = make_document(db, kb)
    db.add(Chunk(document_id=doc.id, kb_id=kb.id, chunk_index=0, text="t", token_count=1,
                 strategy="test"))  # fmt: skip
    conversation = Conversation(user_id=user.id, kb_id=kb.id, title="Q")
    db.add(conversation)
    db.flush()
    db.add(Message(conversation_id=conversation.id, role="user", content="hi"))
    db.flush()

    db.delete(user)  # passive_deletes: one DELETE; PostgreSQL removes the children
    db.flush()

    for model, column in [
        (KnowledgeBase, KnowledgeBase.owner_id),
        (Document, Document.kb_id),
        (Chunk, Chunk.kb_id),
        (Conversation, Conversation.user_id),
    ]:
        key = user.id if column.key in ("owner_id", "user_id") else kb.id
        assert db.scalar(select(func.count()).select_from(model).where(column == key)) == 0
    remaining = select(func.count()).select_from(Message)
    assert db.scalar(remaining.where(Message.conversation_id == conversation.id)) == 0


def test_keyword_search_uses_the_generated_column(db):
    kb = make_kb(db, make_user(db))
    doc = make_document(db, kb)
    db.add_all(
        [
            Chunk(document_id=doc.id, kb_id=kb.id, chunk_index=0, token_count=12,
                  strategy="test", text="Employees may carry forward up to 10 days of leave."),
            Chunk(document_id=doc.id, kb_id=kb.id, chunk_index=1, token_count=10,
                  strategy="test", text="Expense claims are due within 30 days."),
        ]
    )  # fmt: skip
    db.flush()

    query = func.websearch_to_tsquery("english", "carried forward leaves")  # stemmed match
    hits = db.scalars(
        select(Chunk.chunk_index).where(Chunk.kb_id == kb.id, Chunk.search_vector.op("@@")(query))
    ).all()
    assert hits == [0]


def test_search_vector_has_a_gin_index(db):
    definition = db.scalar(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_chunks_search_vector'")
    )
    assert "USING gin" in definition


def test_read_sessions_run_without_a_transaction(test_engine):
    # D27: autocommit read sessions send no BEGIN, so nothing is left open after a query.
    with build_read_session_factory(test_engine)() as session:
        assert session.execute(text("SELECT 1")).scalar() == 1
        raw = session.connection().connection.driver_connection
        assert raw.autocommit is True
        assert raw.info.transaction_status.name == "IDLE"
