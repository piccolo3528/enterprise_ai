"""Schema checks that need no database: the models compile to the intended PostgreSQL DDL."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from app.db.base import Base
from app.db.session import build_read_session_factory, direct_url
from app.models import Chunk, Document, KnowledgeBase, User

DIALECT = postgresql.dialect()


def ddl(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=DIALECT))


def test_all_tables_are_registered():
    assert set(Base.metadata.tables) == {
        "users",
        "knowledge_bases",
        "documents",
        "chunks",
        "conversations",
        "messages",
    }


def test_constraints_get_predictable_names():
    sql = ddl(Document)
    assert "CONSTRAINT pk_documents PRIMARY KEY" in sql
    assert "CONSTRAINT fk_documents_kb_id_knowledge_bases FOREIGN KEY" in sql
    assert "CONSTRAINT uq_documents_kb_id_sha256 UNIQUE (kb_id, sha256)" in sql
    assert "CONSTRAINT ck_documents_status CHECK" in sql


def test_child_rows_are_deleted_by_the_database():
    for model in (KnowledgeBase, Document, Chunk):
        assert "ON DELETE CASCADE" in ddl(model)


def test_markdown_is_an_allowed_file_type():
    assert "'md'" in ddl(Document)


def test_search_vector_is_generated_and_indexed_but_not_loaded_by_default():
    sql = ddl(Chunk)
    assert "GENERATED ALWAYS AS (to_tsvector('english', text)) STORED" in sql
    gin = {ix.name: ix for ix in Chunk.__table__.indexes}["ix_chunks_search_vector"]
    assert gin.dialect_options["postgresql"]["using"] == "gin"
    assert Chunk.search_vector.property.deferred


def test_document_metadata_column_is_named_metadata():
    # `metadata` is reserved on SQLAlchemy models, so the attribute is doc_metadata.
    assert Document.__table__.c.metadata.name == "metadata"
    assert Document.doc_metadata.property.columns[0].name == "metadata"


def test_emails_must_be_stored_lowercase():
    assert "CHECK (email = lower(email))" in ddl(User)


def test_relationships_never_lazy_load():
    # Every hidden lazy load would be an extra network round trip.
    for mapper in Base.registry.mappers:
        for rel in mapper.relationships:
            assert rel.lazy == "raise", f"{mapper.class_.__name__}.{rel.key}"


def test_ids_are_generated_in_python():
    user = User(email="a@example.com", password_hash="x", full_name="A")
    assert user.id is None  # default applies at insert...
    assert User.__table__.c.id.default.arg.__name__ == "uuid4"  # ...from uuid.uuid4, client-side


def test_direct_url_drops_the_pooler_suffix():
    pooled = "postgresql+psycopg://u:p@ep-cool-name-123-pooler.ap-southeast-1.aws.neon.tech/db?x=1"
    assert direct_url(pooled) == (
        "postgresql+psycopg://u:p@ep-cool-name-123.ap-southeast-1.aws.neon.tech/db?x=1"
    )


def test_read_sessions_refuse_writes():
    engine = create_engine("postgresql+psycopg://u:p@127.0.0.1:5999/none")  # never connects
    read_session: Session = build_read_session_factory(engine)()
    read_session.add(User(email="a@example.com", password_hash="x", full_name="A"))
    with pytest.raises(RuntimeError, match="read-only session"):
        read_session.flush()  # refused before any SQL is sent
    engine.dispose()
