"""Password hashing and session tokens (ARCHITECTURE section 4.8).

Passwords: Argon2id with argon2-cffi's defaults (64 MiB memory, 3 passes, 4 lanes; RFC 9106).
Checking one takes ~0.1 s on this laptop: unnoticeable at login, but it makes guessing passwords
from a stolen database very slow, and each hash has its own random salt.

Sessions: a JWT (a signed, tamper-proof token) holding the user's id and an expiry time. The
browser keeps it in an httpOnly cookie, so JavaScript, including injected scripts, can't read it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

# A real hash of a random password, checked when the email doesn't exist. Login then takes the
# same ~0.1 s whether or not the account exists, so response timing can't reveal which emails
# are registered.
_DUMMY_HASH = _hasher.hash(uuid.uuid4().hex)

ALGORITHM = "HS256"
SESSION_COOKIE = "session"


class InvalidTokenError(Exception):
    """The token is missing, expired, tampered with, or malformed."""


def hash_password(password: str) -> str:
    """E.g. "$argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>": the settings travel with the hash."""
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-effort check. Pass None for an unknown user: a dummy hash is checked instead."""
    try:
        _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return password_hash is not None


def needs_rehash(password_hash: str) -> bool:
    """True if the hash was made with weaker settings than today's (upgrade it at next login)."""
    return _hasher.check_needs_rehash(password_hash)


def create_access_token(user_id: uuid.UUID, secret: str, expires_minutes: int) -> str:
    now = datetime.now(UTC)
    claims = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=expires_minutes)}
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, secret: str) -> uuid.UUID:
    """Return the user id inside a valid token, or raise InvalidTokenError."""
    try:
        claims = jwt.decode(
            token,
            secret,
            # Only our algorithm. Accepting whatever the token's header names allows the classic
            # attack of a token signed with "none", or with a different key type.
            algorithms=[ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidTokenError(type(exc).__name__) from None
