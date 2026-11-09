"""Sign up, sign in, sign out, and "who am I?".

These routes are plain `def`, not `async def`: hashing a password takes ~0.1 s of CPU, and FastAPI
runs `def` routes in a worker thread so other requests aren't blocked meanwhile.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, DbSession, SettingsDep
from app.core.config import Settings
from app.core.errors import UnauthorizedError
from app.core.security import SESSION_COOKIE, create_access_token
from app.schemas.auth import LoginRequest, RegisterRequest, UserOut
from app.services.auth import authenticate, register_user

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_PATH = "/api"  # only sent to the API, never with page or asset requests


def _set_session_cookie(response: Response, user_id: uuid.UUID, settings: Settings) -> None:
    token = create_access_token(
        user_id, settings.jwt_secret.get_secret_value(), settings.jwt_expire_minutes
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.jwt_expire_minutes * 60,
        path=_COOKIE_PATH,
        httponly=True,  # JavaScript can't read it, so injected scripts can't steal it
        secure=settings.cookie_secure,  # HTTPS only (browsers treat localhost as secure)
        samesite="strict",  # never sent with requests started by another website (CSRF)
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, response: Response, db: DbSession, settings: SettingsDep):
    """Create an account and sign in straight away."""
    user = register_user(db, email=body.email, password=body.password, full_name=body.full_name)
    _set_session_cookie(response, user.id, settings)
    return user


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, response: Response, db: DbSession, settings: SettingsDep):
    user = authenticate(db, email=body.email, password=body.password)
    if user is None:
        # One message for "no such email" and "wrong password": the login form can't be used
        # to find out who has an account.
        raise UnauthorizedError("Incorrect email or password.")
    _set_session_cookie(response, user.id, settings)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, settings: SettingsDep) -> None:
    """Remove the session cookie. Works even if the session has already expired."""
    response.delete_cookie(
        SESSION_COOKIE,
        path=_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    """The signed-in user. The frontend calls this on load to know whether you're signed in."""
    return user
