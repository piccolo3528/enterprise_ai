"""Password hashing and session tokens."""

from __future__ import annotations

import base64
import json
import uuid

import jwt
import pytest

from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    needs_rehash,
    verify_password,
)

SECRET = "unit-test-secret-that-is-long-enough-0123456789"


def test_hash_is_argon2id_and_never_contains_the_password():
    h = hash_password("correct horse battery staple")
    assert h.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert "correct horse" not in h


def test_same_password_hashes_differently_each_time():
    # A random salt per hash: identical passwords don't produce identical hashes.
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_accepts_the_right_password_only():
    h = hash_password("right-password")
    assert verify_password(h, "right-password")
    assert not verify_password(h, "wrong-password")
    assert not verify_password(h, "Right-password")


def test_unknown_user_is_rejected_after_a_real_check():
    # None = no such account: a dummy hash is still checked, so timing reveals nothing.
    assert not verify_password(None, "anything")


def test_garbage_hash_is_rejected_not_crashing():
    assert not verify_password("not-a-hash", "anything")


def test_current_hashes_do_not_need_rehashing():
    assert not needs_rehash(hash_password("x" * 10))
    weaker = "$argon2id$v=19$m=8,t=1,p=1$c29tZXNhbHQ$cGxhY2Vob2xkZXJoYXNo"
    assert needs_rehash(weaker)


def test_token_round_trip():
    user_id = uuid.uuid4()
    assert decode_access_token(create_access_token(user_id, SECRET, 60), SECRET) == user_id


def test_expired_token_is_rejected():
    token = create_access_token(uuid.uuid4(), SECRET, expires_minutes=-1)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SECRET)


def test_token_signed_with_another_secret_is_rejected():
    token = create_access_token(uuid.uuid4(), "some-other-secret-that-is-long-enough-012345", 60)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SECRET)


def test_tampered_payload_is_rejected():
    # Swap in another user's id but keep the original signature.
    header, payload, signature = create_access_token(uuid.uuid4(), SECRET, 60).split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["sub"] = str(uuid.uuid4())
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    with pytest.raises(InvalidTokenError):
        decode_access_token(f"{header}.{forged}.{signature}", SECRET)


def test_unsigned_alg_none_token_is_rejected():
    token = jwt.encode({"sub": str(uuid.uuid4()), "iat": 0, "exp": 9_999_999_999}, None, "none")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SECRET)


def test_token_without_expiry_is_rejected():
    token = jwt.encode({"sub": str(uuid.uuid4()), "iat": 0}, SECRET, "HS256")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SECRET)


def test_malformed_token_is_rejected():
    for bad in ["", "abc", "a.b.c"]:
        with pytest.raises(InvalidTokenError):
            decode_access_token(bad, SECRET)
