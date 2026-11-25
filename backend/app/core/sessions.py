"""Which session tokens are still valid: token versions, cached per process (M16, D83).

Every session token carries the user's `token_version` (core/security.py). Changing the password
increments the version in the database, so tokens issued before it are refused everywhere:
"sign out everywhere" (closes L27).

**Checking it without a query per request.** Reading the version from PostgreSQL on every request
would cost one round trip (~60 ms to Neon Singapore) on routes that read nothing else today.
Instead this process keeps `user id -> version` in memory: the first request of a user after a
server start reads it once, then it is only changed here, by the routes that bump it. That is
exact for one server process, which is how the app runs (ARCHITECTURE section 8.1). With
several worker processes, a version bumped in one would be unseen by the others until they
restart: the upgrade is to read it per request (or share it via a store), and it's logged (L81).
"""

from __future__ import annotations

import threading
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


def load_token_version(db: Session, user_id: uuid.UUID) -> int | None:
    """The user's current version from the database; None if the account doesn't exist.
    One primary-key read. Unit tests replace this function (they never touch the network)."""
    return db.scalar(select(User.token_version).where(User.id == user_id))


class TokenVersions:
    """user id -> current token version, for this process."""

    def __init__(self) -> None:
        self._versions: dict[uuid.UUID, int] = {}
        self._lock = threading.Lock()
        self.loads = 0  # database reads so far (tests and timings)

    def current(self, db: Session, user_id: uuid.UUID) -> int | None:
        with self._lock:
            known = self._versions.get(user_id)
        if known is not None:
            return known
        version = load_token_version(db, user_id)
        with self._lock:
            self.loads += 1
            if version is not None:
                # setdefault: a concurrent bump that landed meanwhile wins over this older read
                version = self._versions.setdefault(user_id, version)
        return version

    def set(self, user_id: uuid.UUID, version: int) -> None:
        """After a sign-in (the row was just read) or a bump (it was just written)."""
        with self._lock:
            self._versions[user_id] = version
