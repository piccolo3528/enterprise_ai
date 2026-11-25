"""Authorization matrix, cross-user (M16): user B calls every route with user A's real ids.

Every "owned" route (tests/unit/test_security_checklist.py ROUTES) must answer 404, exactly as
for an id that doesn't exist, and must not reach the LLM or Qdrant on the way. Afterwards A's
data is unchanged. Runs on the Neon test branch, rolled back after the test.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db, get_llm, get_read_db, get_vector_store
from app.factory import create_app
from app.models import Conversation, Document, KnowledgeBase
from tests.helpers import act_as, live_settings, make_user, save
from tests.integration.test_schema import make_document
from tests.unit.test_security_checklist import BODIES, ROUTES

pytestmark = pytest.mark.live


class Untouchable:
    """Stands in for the LLM and Qdrant: any use fails the test."""

    def __getattr__(self, name):
        pytest.fail(f"a refused request reached {name}()")


@pytest.fixture
def setup(db):
    settings = live_settings()
    app = create_app(settings, warm_up=False)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_read_db] = lambda: db
    app.dependency_overrides[get_llm] = Untouchable
    app.dependency_overrides[get_vector_store] = Untouchable
    alice, bob = make_user(db, "Alice"), make_user(db, "Bob")
    kb = save(db, KnowledgeBase(owner_id=alice.id, name="Alice's KB"))
    document = make_document(db, kb, b"alice's secret", status="ready", chunk_count=0)
    conversation = save(db, Conversation(user_id=alice.id, kb_id=kb.id, title="Alice's chat"))
    db.commit()
    with TestClient(app, base_url="https://testserver") as client:
        client.secret = settings.jwt_secret.get_secret_value()
        act_as(client, bob)
        yield client, {"kb_id": kb.id, "document_id": document.id,
                       "conversation_id": conversation.id}  # fmt: skip


def test_bob_gets_404_on_every_route_that_names_alices_data(setup, db):
    client, ids = setup
    owned = [route for route, kind in ROUTES.items() if kind == "owned"]
    results = {}
    for method, path in owned:
        url = path.format(**ids)
        kwargs = {"json": BODIES.get((method, path))}
        if path.endswith("/documents") and method == "POST":
            kwargs = {"files": {"file": ("x.txt", b"hello", "text/plain")}}
        response = client.request(method, url, **kwargs)
        results[(method, path)] = (response.status_code, response.json()["error"]["code"])
    assert results == {route: (404, "not_found") for route in owned}

    # Nothing of Alice's changed (the transaction is still open: these see the test's writes).
    db.expire_all()
    assert db.get(KnowledgeBase, ids["kb_id"]).name == "Alice's KB"
    assert db.get(Document, ids["document_id"]).status == "ready"
    assert db.get(Conversation, ids["conversation_id"]).title == "Alice's chat"


def test_bobs_own_lists_and_stats_dont_include_alices_data(setup):
    client, ids = setup
    assert client.get("/api/knowledge-bases").json()["items"] == []
    stats = client.get("/api/stats").json()
    assert stats["knowledge_bases"] == stats["documents"] == stats["conversations"] == 0
