"""Token versions (sign out everywhere, M16) and the settings-page schemas, without a database.

The autouse fixture in tests/unit/conftest.py stands in for the database read of a user's
version: the dict it returns is "the database".
"""

from __future__ import annotations

import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import SESSION_ENDED
from app.core.security import (
    ALGORITHM,
    SESSION_COOKIE,
    InvalidTokenError,
    create_access_token,
    decode_session,
)
from app.core.sessions import TokenVersions
from app.factory import create_app
from app.schemas.answers import AskRequest
from app.schemas.auth import Preferences, PreferencesUpdate, ProfileUpdate, UserOut
from app.services import rag
from tests.helpers import FAKE_JWT_SECRET, make_settings

USER = uuid.uuid4()


def test_tokens_carry_the_version_and_old_tokens_count_as_version_0():
    token = create_access_token(USER, FAKE_JWT_SECRET, 5, version=3)
    assert decode_session(token, FAKE_JWT_SECRET) == (USER, 3)
    pre_m16 = jwt.encode(
        {"sub": str(USER), "iat": 1, "exp": 4_000_000_000}, FAKE_JWT_SECRET, algorithm=ALGORITHM
    )
    assert decode_session(pre_m16, FAKE_JWT_SECRET) == (USER, 0)


def test_a_token_with_a_non_integer_version_is_invalid():
    bad = jwt.encode({"sub": str(USER), "ver": "1", "iat": 1, "exp": 4_000_000_000},
                     FAKE_JWT_SECRET, algorithm=ALGORITHM)  # fmt: skip
    with pytest.raises(InvalidTokenError):
        decode_session(bad, FAKE_JWT_SECRET)


def test_versions_are_read_once_per_user_then_kept_in_memory(token_versions_without_a_database):
    token_versions_without_a_database[USER] = 2
    versions = TokenVersions()
    assert versions.current(None, USER) == 2
    token_versions_without_a_database[USER] = 9  # changed behind our back: not re-read
    assert versions.current(None, USER) == 2 and versions.loads == 1
    versions.set(USER, 3)  # a bump made by this process
    assert versions.current(None, USER) == 3 and versions.loads == 1


@pytest.fixture
def client():
    with TestClient(create_app(make_settings(), warm_up=False)) as c:
        yield c


# A malformed conversation id is 404 without a database query, so "404" = the session was
# accepted and "401" = refused.


def test_an_older_token_version_is_signed_out_with_a_clear_message(
    client, token_versions_without_a_database
):
    token_versions_without_a_database[USER] = 1
    client.cookies.set(SESSION_COOKIE, create_access_token(USER, FAKE_JWT_SECRET, 5, version=0))
    response = client.get("/api/conversations/not-a-uuid")
    assert response.status_code == 401
    assert response.json()["error"]["message"] == SESSION_ENDED
    client.cookies.set(SESSION_COOKIE, create_access_token(USER, FAKE_JWT_SECRET, 5, version=1))
    assert client.get("/api/conversations/not-a-uuid").status_code == 404  # accepted


def test_a_deleted_account_is_signed_out(client, token_versions_without_a_database, monkeypatch):
    from app.core import sessions

    monkeypatch.setattr(sessions, "load_token_version", lambda db, user_id: None)
    client.cookies.set(SESSION_COOKIE, create_access_token(USER, FAKE_JWT_SECRET, 5))
    response = client.get("/api/conversations/not-a-uuid")
    assert response.status_code == 401 and "expired" in response.json()["error"]["message"]


def test_a_bump_in_this_process_ends_old_sessions_at_once(client):
    client.cookies.set(SESSION_COOKIE, create_access_token(USER, FAKE_JWT_SECRET, 5, version=0))
    assert client.get("/api/conversations/not-a-uuid").status_code == 404
    client.app.state.token_versions.set(USER, 1)  # what the password route does
    assert client.get("/api/conversations/not-a-uuid").status_code == 401


# --- preferences and profile ---------------------------------------------------------------------


def test_preferences_fill_defaults_and_ignore_unknown_stored_keys():
    assert Preferences.model_validate({"search_top_k": 5, "removed_pref": 1}).model_dump() == {
        "search_mode": "hybrid", "search_top_k": 5, "search_min_score": None,
        "chat_multi_query": True,
    }  # fmt: skip


@pytest.mark.parametrize(
    "body",
    [{"search_mode": "fuzzy"}, {"search_top_k": 0}, {"search_top_k": 51},
     {"search_min_score": 1.5}, {"theme": "dark"}],
)  # fmt: skip
def test_bad_preference_updates_are_refused(body):
    with pytest.raises(ValidationError):
        PreferencesUpdate.model_validate(body)


def test_only_the_fields_sent_are_updated_and_null_clears_the_minimum_score():
    update = PreferencesUpdate.model_validate({"search_min_score": None})
    assert update.model_dump(exclude_unset=True) == {"search_min_score": None}


@pytest.mark.parametrize("body", [{"full_name": "   "}, {"email": "new@example.com"}])
def test_profile_updates_refuse_blank_names_and_email_changes(body):
    with pytest.raises(ValidationError):
        ProfileUpdate.model_validate(body)


def test_the_user_out_never_shows_the_hash_or_the_token_version():
    assert set(UserOut.model_fields) == {"id", "email", "full_name", "created_at", "preferences"}


def test_a_question_can_turn_extra_phrasings_off_but_not_on():
    on, off = make_settings(multi_query_enabled=True), make_settings(multi_query_enabled=False)
    assert rag.answer_settings(on).multi_query is True
    assert rag.answer_settings(on, None).multi_query is True
    assert rag.answer_settings(on, False).multi_query is False
    assert rag.answer_settings(off, True).multi_query is False
    assert AskRequest.model_validate({"question": "x", "multi_query": False}).multi_query is False
