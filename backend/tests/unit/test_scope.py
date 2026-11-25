"""Searching across all of a user's knowledge bases (M16b), without a database: the scope check
and the filters each store receives. End to end (real search, cross-owner isolation) is
tests/integration/test_all_scope_api.py."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.services import keyword_search, retrieval
from app.services.vector_store import VectorStore

OWNER, KB, DOC = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


class NoDatabase:
    def __getattr__(self, name):
        pytest.fail(f"the database was used ({name})")


def test_all_scope_without_a_document_needs_no_query():
    retrieval.check_scope(NoDatabase(), OWNER, None, None)


class Recorder:
    """Records the SQL and parameters of each execute; returns no rows."""

    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        return SimpleNamespace(all=lambda: [])


@pytest.mark.parametrize(("kb_id", "has_kb_filter"), [(KB, True), (None, False)])
def test_keyword_search_filters_by_owner_always_and_by_kb_only_when_given(kb_id, has_kb_filter):
    db = Recorder()
    keyword_search.keyword_search(db, owner_id=OWNER, kb_id=kb_id, query="leave", limit=5)
    sql, params = db.calls[0]
    assert "kb.owner_id = :owner_id" in sql and params["owner_id"] == OWNER
    assert ("c.kb_id = :kb_id" in sql) is has_kb_filter
    assert ("kb_id" in params) is has_kb_filter


@pytest.mark.parametrize(("kb_id", "keys"), [(KB, {"owner_id", "kb_id"}), (None, {"owner_id"})])
def test_vector_search_always_filters_by_owner(kb_id, keys):
    seen = {}

    def query_points(collection, *, query, query_filter, limit, with_payload):
        seen["keys"] = {condition.key for condition in query_filter.must}
        return SimpleNamespace(points=[])

    store = VectorStore(SimpleNamespace(query_points=query_points), "chunks")
    store.search([0.0], owner_id=OWNER, kb_id=kb_id, limit=5)
    assert seen["keys"] == keys
