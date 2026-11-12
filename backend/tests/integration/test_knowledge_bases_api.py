"""/api/knowledge-bases against PostgreSQL on the Neon test branch (every test rolled back).

The heart of this file is the cross-user matrix: Bob must not be able to read, list, rename or
delete Alice's knowledge base, and the answers he gets must not even reveal that it exists.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.deps import get_db, get_read_db, get_vector_store
from app.factory import create_app
from app.models import Conversation, Document, KnowledgeBase, Message, User
from tests.helpers import act_as, live_settings, save

pytestmark = pytest.mark.live

URL = "/api/knowledge-bases"


@pytest.fixture
def client(db, vector_store):
    settings = live_settings()
    app = create_app(settings, warm_up=False)
    app.dependency_overrides[get_vector_store] = lambda: vector_store
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_read_db] = lambda: db
    with TestClient(app, base_url="https://testserver") as c:
        c.secret = settings.jwt_secret.get_secret_value()
        yield c


def create(client, name="HR Policies", description=None):
    return client.post(URL, json={"name": name, "description": description})


def add_document(db, kb_id, content: bytes) -> Document:
    document = Document(
        kb_id=kb_id,
        original_filename="policy.md",
        stored_path=f"{kb_id}/{uuid.uuid4()}.md",
        file_type="md",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )
    return save(db, document)


def add_conversation(db, user, kb_id) -> Conversation:
    conversation = save(db, Conversation(user_id=user.id, kb_id=kb_id, title="Leave question"))
    save(db, Message(conversation_id=conversation.id, role="user", content="How many days?"))
    return conversation


# --- create / read -------------------------------------------------------------------------------


def test_create_then_read_back(client, alice):
    act_as(client, alice)
    response = create(client, name="  HR   Policies ", description="  Leave, travel  ")
    assert response.status_code == 201
    kb = response.json()
    assert kb["name"] == "HR Policies"
    assert kb["description"] == "Leave, travel"
    assert kb["document_count"] == 0 and kb["conversation_count"] == 0
    assert set(kb) == {
        "id",
        "name",
        "description",
        "document_count",
        "conversation_count",
        "created_at",
        "updated_at",
    }  # no owner_id

    assert client.get(f"{URL}/{kb['id']}").json() == kb
    assert client.get(URL).json() == {"items": [kb]}


def test_list_is_newest_change_first_and_counts_are_per_knowledge_base(client, db, alice):
    act_as(client, alice)
    old = uuid.UUID(create(client, name="Old").json()["id"])
    new = uuid.UUID(create(client, name="New").json()["id"])
    # Inside one test transaction now() never moves, so set distinct times by hand.
    now = datetime.now(UTC)
    db.get(KnowledgeBase, old).updated_at = now - timedelta(days=2)
    db.get(KnowledgeBase, new).updated_at = now - timedelta(days=1)
    db.commit()
    add_document(db, old, b"one")
    add_document(db, old, b"two")
    add_conversation(db, alice, old)

    items = client.get(URL).json()["items"]
    assert [(i["name"], i["document_count"], i["conversation_count"]) for i in items] == [
        ("New", 0, 0),
        ("Old", 2, 1),
    ]


def test_names_are_unique_per_user_ignoring_case(client, alice, bob):
    act_as(client, alice)
    assert create(client, name="HR Policies").status_code == 201
    duplicate = create(client, name="hr   POLICIES")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"] == {
        "code": "conflict",
        "message": 'You already have a knowledge base called "hr POLICIES".',
        "request_id": duplicate.headers["x-request-id"],
    }

    act_as(client, bob)  # someone else may use the same name
    assert create(client, name="HR Policies").status_code == 201


def test_invalid_input_is_a_422_never_a_500(client, alice):
    act_as(client, alice)
    for body in ({"name": ""}, {"name": "nul\x00byte"}, {"name": "x" * 121}, {}):
        response = client.post(URL, json=body)
        assert response.status_code == 422, body
    assert client.get(URL).json() == {"items": []}


# --- update --------------------------------------------------------------------------------------


def test_rename_and_describe(client, db, alice):
    act_as(client, alice)
    kb_id = create(client, name="HR", description="Old text").json()["id"]
    add_document(db, uuid.UUID(kb_id), b"doc")
    before = datetime.now(UTC) - timedelta(days=1)
    db.get(KnowledgeBase, uuid.UUID(kb_id)).updated_at = before
    db.commit()

    renamed = client.patch(f"{URL}/{kb_id}", json={"name": "People team"})
    assert renamed.status_code == 200
    body = renamed.json()
    assert body["name"] == "People team"
    assert body["description"] == "Old text"  # not sent, so unchanged
    assert body["document_count"] == 1  # counts come back from the UPDATE … RETURNING
    assert datetime.fromisoformat(body["updated_at"]) > before

    cleared = client.patch(f"{URL}/{kb_id}", json={"description": None}).json()
    assert cleared["description"] is None and cleared["name"] == "People team"


def test_changing_only_the_case_of_your_own_name_is_allowed(client, alice):
    act_as(client, alice)
    kb_id = create(client, name="hr").json()["id"]
    assert client.patch(f"{URL}/{kb_id}", json={"name": "HR"}).json()["name"] == "HR"


def test_renaming_onto_another_of_your_names_is_a_conflict(client, alice):
    act_as(client, alice)
    create(client, name="Finance")
    kb_id = create(client, name="Legal").json()["id"]
    response = client.patch(f"{URL}/{kb_id}", json={"name": "FINANCE"})
    assert response.status_code == 409
    assert client.get(f"{URL}/{kb_id}").json()["name"] == "Legal"  # rolled back


def test_an_empty_patch_is_rejected(client, alice):
    act_as(client, alice)
    kb_id = create(client).json()["id"]
    assert client.patch(f"{URL}/{kb_id}", json={}).status_code == 422
    assert client.patch(f"{URL}/{kb_id}", json={"name": None}).status_code == 422


# --- delete --------------------------------------------------------------------------------------


def test_delete_removes_everything_inside(client, db, alice):
    act_as(client, alice)
    kb_id = uuid.UUID(create(client).json()["id"])
    document_id = add_document(db, kb_id, b"doc").id
    conversation_id = add_conversation(db, alice, kb_id).id

    assert client.delete(f"{URL}/{kb_id}").status_code == 204
    assert client.get(f"{URL}/{kb_id}").status_code == 404
    assert client.delete(f"{URL}/{kb_id}").status_code == 404  # already gone
    db.expire_all()
    remaining = {
        "knowledge base": select(KnowledgeBase).where(KnowledgeBase.id == kb_id),
        "document": select(Document).where(Document.id == document_id),
        "conversation": select(Conversation).where(Conversation.id == conversation_id),
        "message": select(Message).where(Message.conversation_id == conversation_id),
    }
    for what, query in remaining.items():
        count = db.scalar(select(func.count()).select_from(query.subquery()))
        assert count == 0, what
    assert db.get(User, alice.id) is not None  # the owner stays


# --- tenant isolation ----------------------------------------------------------------------------


def error_without_request_id(response):
    error = response.json()["error"]
    error.pop("request_id")
    return response.status_code, error


@pytest.mark.parametrize(
    ("method", "body"),
    [("get", None), ("patch", {"name": "Taken over"}), ("delete", None)],
)
def test_another_users_knowledge_base_looks_exactly_like_a_missing_one(
    client, db, alice, bob, method, body
):
    act_as(client, alice)
    kb = create(client, name="Alice private", description="Secret plans").json()
    add_document(db, uuid.UUID(kb["id"]), b"alice's file")

    act_as(client, bob)
    theirs = client.request(method, f"{URL}/{kb['id']}", json=body)
    missing = client.request(method, f"{URL}/{uuid.uuid4()}", json=body)
    assert error_without_request_id(theirs) == error_without_request_id(missing)
    assert theirs.status_code == 404
    assert "Alice" not in theirs.text and "Secret" not in theirs.text
    assert client.get(URL).json() == {"items": []}  # and it isn't in Bob's list

    act_as(client, alice)  # nothing changed for Alice
    after = client.get(f"{URL}/{kb['id']}").json()
    assert (after["name"], after["description"], after["document_count"]) == (
        "Alice private",
        "Secret plans",
        1,
    )
