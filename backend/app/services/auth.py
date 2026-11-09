"""Registering and authenticating users. No FastAPI imports: routes handle HTTP and cookies."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.core.security import hash_password, needs_rehash, verify_password
from app.models import User


def normalize_email(email: str) -> str:
    # Stored lowercase (the database enforces it), so "Ana@X.com" and "ana@x.com" are one account.
    return email.strip().lower()


def register_user(db: Session, *, email: str, password: str, full_name: str) -> User:
    user = User(
        email=normalize_email(email),
        password_hash=hash_password(password),
        full_name=full_name,
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
