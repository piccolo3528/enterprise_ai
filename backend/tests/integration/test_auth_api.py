"""The /api/auth endpoints against PostgreSQL on the Neon test branch (every test rolled back)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_db, get_read_db
from app.core.config import load_settings
from app.core.security import SESSION_COOKIE, create_access_token
from app.factory import create_app
from app.models import User

pytestmark = pytest.mark.live

PASSWORD = "a-long-test-passphrase"


@pytest.fixture
def client(db):
    """The real app, with its database sessions replaced by the rolled-back test session."""
    settings = load_settings()
    app = create_app(settings, warm_up=False)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_read_db] = lambda: db
    # https: the session cookie is Secure, and a client only sends Secure cookies over HTTPS.
    with TestClient(app, base_url="https://testserver") as c:
        c.settings = settings
        yield c


def register(client, email=None, password=PASSWORD, full_name="Test User"):
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    return client.post(
        "/api/auth/register", json={"email": email, "password": password, "full_name": full_name}
    )


def test_register_creates_the_user_and_signs_in(client, db):
    response = register(client, email="New.User@Example.com")
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new.user@example.com"  # stored lowercase
    # no password hash, no token version; preferences since M16
    assert set(body) == {"id", "email", "full_name", "created_at", "preferences"}

    stored = db.scalar(select(User).where(User.email == "new.user@example.com"))
    assert stored.password_hash.startswith("$argon2id$")
    assert client.get("/api/auth/me").json()["email"] == "new.user@example.com"


def test_session_cookie_is_locked_down(client):
    cookie = register(client).headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    for attribute in ("HttpOnly", "Secure", "SameSite=strict", "Path=/api", "Max-Age=3600"):
        assert attribute in cookie, attribute


def test_duplicate_email_is_a_conflict_whatever_the_case(client):
    register(client, email="dup@example.com")
    response = register(client, email="DUP@example.com")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_login_with_the_right_password(client):
    register(client, email="login@example.com")
    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/login", json={"email": "LOGIN@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_wrong_password_and_unknown_email_get_the_same_answer(client):
    register(client, email="known@example.com")
    client.post("/api/auth/logout")
    wrong = client.post("/api/auth/login", json={"email": "known@example.com", "password": "nope"})
    unknown = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert "set-cookie" not in wrong.headers


def test_five_wrong_passwords_lock_the_email_even_against_the_right_one(client):
    # M16 (L26): default limits, 5 failures per email in 15 minutes.
    register(client, email="locked@example.com")
    client.post("/api/auth/logout")
    for _ in range(5):
        wrong = client.post("/api/auth/login", json={"email": "locked@example.com",
                                                     "password": "wrong-guess"})  # fmt: skip
        assert wrong.status_code == 401
    right = client.post(
        "/api/auth/login", json={"email": "Locked@example.com", "password": PASSWORD}
    )
    assert right.status_code == 429 and right.json()["error"]["code"] == "rate_limited"
    assert 0 < int(right.headers["Retry-After"]) <= 900
    assert "set-cookie" not in right.headers
    # An unknown email gets the same lock-out as a known one (no account enumeration).
    for _ in range(5):
        client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "x"})
    ghost = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "x"})
    assert ghost.status_code == 429
    assert ghost.json()["error"]["message"].startswith("Too many failed sign-in attempts")
    # Others can still sign in from this address (10 of its 20 failures used).
    register(client, email="other@example.com")
    client.post("/api/auth/logout")
    ok = client.post("/api/auth/login", json={"email": "other@example.com", "password": PASSWORD})
    assert ok.status_code == 200


def test_the_sixth_registration_from_one_address_in_an_hour_is_refused(client):
    for _ in range(5):
        assert register(client).status_code == 201
    refused = register(client)
    assert (
        refused.status_code == 429 and "Too many new accounts" in refused.json()["error"]["message"]
    )


def test_me_requires_a_session(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_logout_clears_the_cookie(client):
    register(client)
    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize(
    "token_for",
    [
        "tampered",  # signature no longer matches
        "expired",
        "deleted user",  # validly signed, but the account no longer exists
    ],
)
def test_bad_sessions_are_rejected(client, token_for):
    secret = client.settings.jwt_secret.get_secret_value()
    if token_for == "tampered":
        register(client)
        token = client.cookies.get(SESSION_COOKIE)[:-4] + "AAAA"
    elif token_for == "expired":
        user_id = uuid.UUID(register(client).json()["id"])
        token = create_access_token(user_id, secret, expires_minutes=-1)
    else:
        token = create_access_token(uuid.uuid4(), secret, expires_minutes=60)
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, token, domain="testserver", path="/api")
    assert client.get("/api/auth/me").status_code == 401


def test_invalid_input_is_rejected_without_echoing_the_password(client):
    response = register(client, password="short7!")
    assert response.status_code == 422
    assert "short7!" not in response.text
    fields = {d["field"] for d in response.json()["error"]["details"]}
    assert fields == {"body.password"}

    assert register(client, email="not-an-email").status_code == 422
    assert register(client, full_name="   ").status_code == 422


def test_login_refuses_non_json_bodies(client):
    # A cross-site HTML form can only send form/text bodies, never application/json without a
    # CORS preflight that this server doesn't allow. So JSON-only endpoints resist CSRF.
    register(client, email="csrf@example.com")
    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/login",
        content=f'{{"email": "csrf@example.com", "password": "{PASSWORD}"}}',
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 422
    assert "set-cookie" not in response.headers
