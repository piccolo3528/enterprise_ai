"""Settings page API (M16): profile, preferences, password change and sign out everywhere,
against the Neon test branch (rolled back after each test)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import SESSION_ENDED, get_db, get_read_db
from app.core.config import load_settings
from app.core.security import SESSION_COOKIE
from app.factory import create_app
from app.models import User

pytestmark = pytest.mark.live

PASSWORD = "a-long-test-passphrase"
NEW_PASSWORD = "another-long-passphrase"


def make_client(db):
    app = create_app(load_settings(), warm_up=False)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_read_db] = lambda: db
    return TestClient(app, base_url="https://testserver")


@pytest.fixture
def client(db):
    with make_client(db) as c:
        email = f"settings-{uuid.uuid4().hex[:8]}@example.com"
        response = c.post(
            "/api/auth/register",
            json={"email": email, "password": PASSWORD, "full_name": "Sam Settings"},
        )
        assert response.status_code == 201
        c.email = email
        yield c


def test_me_shows_default_preferences(client):
    body = client.get("/api/auth/me").json()
    assert body["preferences"] == {
        "search_mode": "hybrid", "search_top_k": 10, "search_min_score": None,
        "chat_multi_query": True,
    }  # fmt: skip
    assert "token_version" not in body and "password_hash" not in body


def test_name_and_preferences_are_saved_and_only_sent_fields_change(client, db):
    response = client.patch("/api/auth/me", json={
        "full_name": "  Sam S.  ",
        "preferences": {"search_mode": "keyword", "search_min_score": 0.4},
    })  # fmt: skip
    assert response.status_code == 200
    assert response.json()["full_name"] == "Sam S."
    client.patch("/api/auth/me", json={"preferences": {"chat_multi_query": False}})
    prefs = client.get("/api/auth/me").json()["preferences"]
    assert prefs == {"search_mode": "keyword", "search_top_k": 10, "search_min_score": 0.4,
                     "chat_multi_query": False}  # fmt: skip
    client.patch("/api/auth/me", json={"preferences": {"search_min_score": None}})
    assert client.get("/api/auth/me").json()["preferences"]["search_min_score"] is None
    stored = db.query(User).filter_by(email=client.email).one()
    assert stored.settings["search_mode"] == "keyword"  # kept in users.settings (JSONB)


@pytest.mark.parametrize(
    "body",
    [{"email": "x@example.com"}, {"preferences": {"search_top_k": 500}},
     {"preferences": {"theme": "dark"}}, {"full_name": " "}],
)  # fmt: skip
def test_invalid_profile_updates_are_refused(client, body):
    response = client.patch("/api/auth/me", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def change(client, current, new):
    return client.post(
        "/api/auth/password", json={"current_password": current, "new_password": new}
    )


def test_a_wrong_or_unchanged_current_password_is_400_not_a_sign_out(client):
    wrong = change(client, "nope", NEW_PASSWORD)
    assert wrong.status_code == 400
    assert wrong.json()["error"]["message"] == "Your current password is incorrect."
    same = change(client, PASSWORD, PASSWORD)
    assert same.status_code == 400 and "different" in same.json()["error"]["message"]
    assert client.get("/api/auth/me").status_code == 200  # still signed in


def test_changing_the_password_ends_every_other_session(client, db):
    old_token = client.cookies.get(SESSION_COOKIE)
    response = change(client, PASSWORD, NEW_PASSWORD)
    assert response.status_code == 204
    assert "HttpOnly" in response.headers["set-cookie"]  # this browser stays signed in
    assert client.get("/api/auth/me").status_code == 200

    # Another device still holding the old cookie: refused by this process at once...
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, old_token)
    refused = client.get("/api/auth/me")
    assert refused.status_code == 401 and refused.json()["error"]["message"] == SESSION_ENDED
    # ...and by a freshly started server, which reads the version from the database.
    with make_client(db) as restarted:
        restarted.cookies.set(SESSION_COOKIE, old_token)
        assert restarted.get("/api/auth/me").status_code == 401
        assert restarted.app.state.token_versions.loads == 1

    client.cookies.clear()
    old = client.post("/api/auth/login", json={"email": client.email, "password": PASSWORD})
    new = client.post("/api/auth/login", json={"email": client.email, "password": NEW_PASSWORD})
    assert (old.status_code, new.status_code) == (401, 200)


def test_sign_out_everywhere_includes_this_browser(client):
    token = client.cookies.get(SESSION_COOKIE)
    response = client.post("/api/auth/logout-all")
    assert response.status_code == 204 and "Max-Age=0" in response.headers["set-cookie"]
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, token)
    assert client.get("/api/auth/me").status_code == 401


def test_the_version_is_read_once_per_user_per_server_start(client, db):
    token = client.cookies.get(SESSION_COOKIE)
    with make_client(db) as restarted:
        restarted.cookies.set(SESSION_COOKIE, token)
        for _ in range(3):
            assert restarted.get("/api/auth/me").status_code == 200
        assert restarted.app.state.token_versions.loads == 1


# --- dashboard stats -----------------------------------------------------------------------------


def test_stats_count_only_your_own_data_in_one_response(client, db):
    from datetime import timedelta

    from sqlalchemy import func, update

    from app.models import Conversation, Message
    from tests.integration.test_schema import make_document, make_kb
    from tests.integration.test_schema import make_user as other_user

    me = db.query(User).filter_by(email=client.email).one()
    kb = make_kb(db, me)
    make_document(db, kb, b"aaaa", status="ready", chunk_count=7)
    make_document(db, kb, b"bb", status="processing")
    make_document(db, kb, b"c", status="failed")
    make_document(db, kb, b"gone", status="deleting")  # leaving: not counted
    chat = Conversation(user_id=me.id, kb_id=kb.id, title="Leave")
    db.add(chat)
    db.flush()
    db.add_all([
        Message(conversation_id=chat.id, role="user", content="q1"),
        Message(conversation_id=chat.id, role="assistant", content="a1", outcome="answered"),
        Message(conversation_id=chat.id, role="user", content="q2"),
        Message(conversation_id=chat.id, role="assistant", content="a2", outcome="not_found"),
    ])  # fmt: skip
    db.flush()
    old = Message(conversation_id=chat.id, role="user", content="q0")
    db.add(old)
    db.flush()
    db.execute(update(Message).where(Message.id == old.id)
               .values(created_at=func.now() - timedelta(days=8)))  # fmt: skip
    stranger = other_user(db)
    make_document(db, make_kb(db, stranger), b"secret", status="ready", chunk_count=99)
    db.commit()

    response = client.get("/api/stats")
    assert response.status_code == 200
    assert response.json() == {
        "knowledge_bases": 1, "documents": 3, "documents_ready": 1, "documents_processing": 1,
        "documents_failed": 1, "chunks": 7, "storage_bytes": 7, "conversations": 1,
        "questions": 3, "questions_7d": 2, "not_found_7d": 1,
    }  # fmt: skip


def test_stats_need_a_session(client):
    client.cookies.clear()
    assert client.get("/api/stats").status_code == 401
