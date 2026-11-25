"""Per-user limits (M16): the sliding-window limiter, and 429s from the routes it guards.

The route tests fill a limiter by hand and expect 429 before any database or LLM work: the app's
database URL points at a closed port, so a request that got further would fail differently.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.errors import RateLimitedError
from app.core.rate_limit import (
    DAY,
    LOGIN_WINDOW,
    MINUTE,
    RateLimits,
    SlidingWindowLimiter,
    describe_wait,
)
from app.core.security import SESSION_COOKIE, create_access_token
from app.factory import create_app
from tests.helpers import FAKE_JWT_SECRET, make_settings


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# --- the limiter ---------------------------------------------------------------------------------


def test_allows_the_limit_then_refuses_until_the_oldest_event_leaves_the_window():
    clock = Clock()
    limiter = SlidingWindowLimiter(3, 60, clock=clock)
    for _ in range(3):
        assert limiter.hit("u") is None
        clock.now += 10  # events at 1000, 1010, 1020
    assert limiter.hit("u") == pytest.approx(30)  # now 1030; the oldest (1000) leaves at 1060
    clock.now = 1059.9
    assert limiter.hit("u") == pytest.approx(0.1)
    clock.now = 1060
    assert limiter.hit("u") is None  # a sliding window: no burst at a minute boundary


def test_refused_attempts_are_not_recorded_and_keys_are_independent():
    clock = Clock()
    limiter = SlidingWindowLimiter(1, 60, clock=clock)
    assert limiter.hit("a") is None
    for _ in range(5):
        assert limiter.hit("a") is not None  # hammering doesn't extend the wait
    assert limiter.hit("b") is None
    clock.now += 60
    assert limiter.hit("a") is None and limiter.count("a") == 1


def test_retry_after_peeks_without_recording_and_reset_clears_a_key():
    clock = Clock()
    limiter = SlidingWindowLimiter(1, 60, clock=clock)
    assert limiter.retry_after("a") is None and limiter.count("a") == 0
    limiter.hit("a")
    assert limiter.retry_after("a") == 60
    limiter.reset("a")
    assert limiter.hit("a") is None


def test_idle_keys_are_swept_so_memory_stays_bounded():
    clock = Clock()
    limiter = SlidingWindowLimiter(5, 60, clock=clock)
    for i in range(999):
        limiter.hit(f"email-{i}")
    clock.now += 61
    limiter.hit("last")  # the 1000th call sweeps keys with nothing in the window
    assert set(limiter._events) == {"last"}


@pytest.mark.parametrize(("limit", "window"), [(0, 60), (1, 0)])
def test_nonsense_limits_are_refused(limit, window):
    with pytest.raises(ValueError):
        SlidingWindowLimiter(limit, window)


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(0.2, "1 seconds"), (40, "40 seconds"), (89.1, "90 seconds"), (900, "15 minutes"),
     (DAY - 1, "about 24 hours")],
)  # fmt: skip
def test_waits_are_described_for_people(seconds, text):
    assert describe_wait(seconds) == text


# --- the policies --------------------------------------------------------------------------------


def limits(clock, **overrides):
    return RateLimits.from_settings(make_settings(**{
        "rate_limit_chat_per_minute": 10, "rate_limit_chat_per_day": 150,
        "rate_limit_uploads_per_hour": 20, "rate_limit_login_failures_per_email": 5,
        "rate_limit_login_failures_per_address": 20, "rate_limit_registrations_per_hour": 5,
        **overrides,
    }), clock=clock)  # fmt: skip


def test_the_defaults_are_the_agreed_numbers():
    from app.core.config import Settings

    names = ("chat_per_minute", "chat_per_day", "uploads_per_hour", "login_failures_per_email",
             "login_failures_per_address", "registrations_per_hour")  # fmt: skip
    defaults = tuple(Settings.model_fields[f"rate_limit_{n}"].default for n in names)
    assert defaults == (10, 150, 20, 5, 20, 5)


def test_questions_are_limited_per_minute_and_per_day():
    clock = Clock()
    lim = limits(clock, rate_limit_chat_per_day=12)
    for _ in range(10):
        lim.question("u")
    with pytest.raises(RateLimitedError) as minute:
        lim.question("u")
    assert "10 questions in a minute" in minute.value.message
    assert minute.value.headers == {"Retry-After": "60"}
    lim.question("other")  # per user
    clock.now += MINUTE
    lim.question("u")
    lim.question("u")  # 12 today
    with pytest.raises(RateLimitedError) as day:
        lim.question("u")
    assert "12 questions in 24 hours" in day.value.message and "about 24 hours" in day.value.message
    assert lim.chat_minute.count("u") == 2  # the refused question used no minute slot


def test_sign_in_failures_lock_the_email_and_success_clears_it():
    clock = Clock()
    lim = limits(clock)
    for _ in range(4):
        lim.check_login("ana@x.com", "1.2.3.4")
        lim.login_failed("ana@x.com", "1.2.3.4")
    lim.login_succeeded("ana@x.com")  # the owner typed it right: their count starts again
    for _ in range(5):
        lim.check_login("ana@x.com", "1.2.3.4")
        lim.login_failed("ana@x.com", "1.2.3.4")
    with pytest.raises(RateLimitedError) as locked:
        lim.check_login("ana@x.com", "5.6.7.8")  # another address: the email is still locked
    assert "Too many failed sign-in attempts" in locked.value.message
    assert locked.value.headers == {"Retry-After": str(int(LOGIN_WINDOW))}
    lim.check_login("bob@x.com", "1.2.3.4")  # the address has 9 of 20: others can sign in
    clock.now += LOGIN_WINDOW
    lim.check_login("ana@x.com", "1.2.3.4")


def test_one_address_guessing_many_emails_is_limited_too():
    clock = Clock()
    lim = limits(clock)
    for i in range(20):
        lim.login_failed(f"user{i}@x.com", "1.2.3.4")
    with pytest.raises(RateLimitedError):
        lim.check_login("new@x.com", "1.2.3.4")
    lim.check_login("new@x.com", "9.9.9.9")


def test_uploads_and_registrations_are_limited():
    clock = Clock()
    lim = limits(clock, rate_limit_uploads_per_hour=2, rate_limit_registrations_per_hour=1)
    lim.upload("u")
    lim.upload("u")
    with pytest.raises(RateLimitedError, match="2 files in the last hour"):
        lim.upload("u")
    lim.registration("1.2.3.4")
    with pytest.raises(RateLimitedError, match="Too many new accounts"):
        lim.registration("1.2.3.4")


# --- the routes: 429 before any database or LLM work ----------------------------------------------

USER = uuid.uuid4()
KB = uuid.uuid4()


@pytest.fixture
def limited():
    """An app whose limits allow one of everything; the test fills them, then calls the route."""
    app = create_app(
        make_settings(**{f"rate_limit_{name}": 1 for name in (
            "chat_per_minute", "chat_per_day", "uploads_per_hour", "login_failures_per_email",
            "login_failures_per_address", "registrations_per_hour")}),
        warm_up=False,
    )  # fmt: skip
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set(SESSION_COOKIE, create_access_token(USER, FAKE_JWT_SECRET, 5))
        yield app, client


def assert_limited(response, message):
    assert response.status_code == 429, response.text
    body = response.json()["error"]
    assert body["code"] == "rate_limited" and message in body["message"]
    assert int(response.headers["Retry-After"]) > 0


@pytest.mark.parametrize(
    "url",
    [f"/api/knowledge-bases/{KB}/ask", f"/api/knowledge-bases/{KB}/conversations",
     f"/api/conversations/{uuid.uuid4()}/messages"],
)  # fmt: skip
def test_every_question_route_is_limited(limited, url):
    app, client = limited
    app.state.limits.question(str(USER))
    assert_limited(client.post(url, json={"question": "How many days?"}), "1 question in")


def test_a_question_without_a_session_is_401_not_429(limited):
    app, client = limited
    app.state.limits.question(str(USER))
    client.cookies.clear()
    response = client.post(f"/api/knowledge-bases/{KB}/ask", json={"question": "x"})
    assert response.status_code == 401


def test_upload_is_limited_before_the_body_is_read(limited, monkeypatch):
    app, client = limited
    from app.services import documents

    monkeypatch.setattr(documents, "require_owned_kb", lambda db, user_id, kb_id: None)
    monkeypatch.setattr(
        documents, "add_document", lambda *a, **k: pytest.fail("the body was read and stored")
    )
    app.state.limits.upload(str(USER))
    response = client.post(
        f"/api/knowledge-bases/{KB}/documents", files={"file": ("a.txt", b"hello", "text/plain")}
    )
    assert_limited(response, "1 file in the last hour")


def test_sign_in_is_refused_while_locked_without_checking_the_password(limited, monkeypatch):
    app, client = limited
    from app.api.routes import auth

    monkeypatch.setattr(auth, "authenticate", lambda *a, **k: pytest.fail("password checked"))
    app.state.limits.login_failed("ana@example.com", "testclient")
    response = client.post(
        "/api/auth/login", json={"email": "Ana@Example.com", "password": "whatever"}
    )
    assert_limited(response, "Too many failed sign-in attempts")


def test_registration_is_limited_per_address(limited):
    app, client = limited
    app.state.limits.registration("testclient")  # TestClient's address
    response = client.post(
        "/api/auth/register",
        json={"email": "new@example.com", "password": "long-enough-pw", "full_name": "New"},
    )
    assert_limited(response, "Too many new accounts")
