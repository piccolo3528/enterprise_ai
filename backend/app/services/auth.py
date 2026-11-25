"""Registering and authenticating users. No FastAPI imports: routes handle HTTP and cookies."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, UnauthorizedError
from app.core.security import hash_password, needs_rehash, verify_password
from app.models import User
from app.schemas.auth import Preferences


def normalize_email(email: str) -> str:
    # Stored lowercase (the database enforces it), so "Ana@X.com" and "ana@x.com" are one account.
    return email.strip().lower()


def register_user(db: Session, *, email: str, password: str, full_name: str) -> User:
    user = User(
        email=normalize_email(email),
        password_hash=hash_password(password),
        full_name=full_name,
        token_version=0,
    )
    db.add(user)
    try:
        # No "does this email exist?" query first: the unique constraint answers that in the
        # same round trip, and it can't be beaten by two sign-ups arriving at the same moment.
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "uq_users_email" in str(exc.orig):
            raise ConflictError("An account with this email already exists.") from None
        raise
    return user


def authenticate(db: Session, *, email: str, password: str) -> User | None:
    """The user if the email and password match, else None. Same effort either way."""
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if not verify_password(user.password_hash if user else None, password):
        return None
    if needs_rehash(user.password_hash):
        # The hashing settings were raised since this password was stored: upgrade it now,
        # the only moment we have the plain password.
        user.password_hash = hash_password(password)
        db.commit()
    return user


# --- Settings page (M16) ------------------------------------------------------------------------

SAME_PASSWORD = "Choose a new password that is different from the current one."
WRONG_PASSWORD = "Your current password is incorrect."


def _user(db: Session, user_id) -> User:
    user = db.get(User, user_id)
    if user is None:  # deleted after the token was issued
        raise UnauthorizedError("Your session has expired. Please sign in again.")
    return user


def update_profile(
    db: Session, user_id, *, full_name: str | None, preferences: dict | None
) -> User:
    """Change the name and/or preferences. `preferences` holds only the fields being changed;
    the result is validated as a whole before it's stored."""
    user = _user(db, user_id)
    if full_name is not None:
        user.full_name = full_name
    if preferences:
        merged = Preferences.model_validate({**(user.settings or {}), **preferences})
        user.settings = merged.model_dump()  # a new dict: SQLAlchemy sees the change
    db.commit()
    return user


def bump_token_version(db: Session, user_id) -> int:
    """End every session of this user (their tokens carry the old version). Done in SQL
    (`token_version + 1 ... RETURNING`), so two bumps at once can't both produce the same
    number."""
    version = db.scalar(
        update(User)
        .where(User.id == user_id)
        .values(token_version=User.token_version + 1)
        .returning(User.token_version)
    )
    if version is None:
        raise UnauthorizedError("Your session has expired. Please sign in again.")
    return version


def change_password(db: Session, user_id, *, current: str, new: str) -> int | None:
    """Check the current password, store the new one and end every other session.
    Returns the new token version, or None if the current password was wrong (the route
    counts that as a failed sign-in: a stolen session can't be used to guess the password).
    """
    user = _user(db, user_id)
    if not verify_password(user.password_hash, current):
        return None
    if current == new:
        raise AppError(SAME_PASSWORD)
    user.password_hash = hash_password(new)
    db.flush()
    version = bump_token_version(db, user_id)
    db.commit()
    return version
