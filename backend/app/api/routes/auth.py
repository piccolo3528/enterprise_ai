"""Sign up, sign in, sign out, "who am I?", and the account settings (M16).

These routes are plain `def`, not `async def`: hashing a password takes ~0.1 s of CPU, and FastAPI
runs `def` routes in a worker thread so other requests aren't blocked meanwhile.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import (
    ClientAddress,
    CurrentUser,
    CurrentUserId,
    DbSession,
    LimitsDep,
    SettingsDep,
    TokenVersionsDep,
)
from app.core.config import Settings
from app.core.errors import AppError, UnauthorizedError
from app.core.security import SESSION_COOKIE, create_access_token
from app.core.sessions import TokenVersions
from app.schemas.auth import LoginRequest, PasswordChange, ProfileUpdate, RegisterRequest, UserOut
from app.services import auth as service
from app.services.auth import authenticate, normalize_email, register_user

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_PATH = "/api"  # only sent to the API, never with page or asset requests


def _set_session_cookie(
    response: Response,
    user_id: uuid.UUID,
    version: int,
    settings: Settings,
    versions: TokenVersions,
) -> None:
    token = create_access_token(
        user_id, settings.jwt_secret.get_secret_value(), settings.jwt_expire_minutes, version
    )
    versions.set(user_id, version)  # just read or written: no lookup on the next request
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.jwt_expire_minutes * 60,
        path=_COOKIE_PATH,
        httponly=True,  # JavaScript can't read it, so injected scripts can't steal it
        secure=settings.cookie_secure,  # HTTPS only (browsers treat localhost as secure)
        samesite="strict",  # never sent with requests started by another website (CSRF)
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path=_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterRequest,
    response: Response,
    db: DbSession,
    settings: SettingsDep,
    limits: LimitsDep,
    address: ClientAddress,
    versions: TokenVersionsDep,
):
    """Create an account and sign in straight away. 429 after
    RATE_LIMIT_REGISTRATIONS_PER_HOUR new accounts from one address."""
    limits.registration(address)
    user = register_user(db, email=body.email, password=body.password, full_name=body.full_name)
    _set_session_cookie(response, user.id, user.token_version, settings, versions)
    return user


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    response: Response,
    db: DbSession,
    settings: SettingsDep,
    limits: LimitsDep,
    address: ClientAddress,
    versions: TokenVersionsDep,
):
    """Sign in. After 5 wrong passwords for one email (or 20 from one address) in 15 minutes,
    429 until the oldest failure is 15 minutes old: guessing slows to a few tries per quarter
    hour instead of ~10 a second (L26)."""
    email = normalize_email(body.email)
    limits.check_login(email, address)  # before the hash check: a locked-out guess costs nothing
    user = authenticate(db, email=email, password=body.password)
    if user is None:
        limits.login_failed(email, address)
        # One message for "no such email" and "wrong password": the login form can't be used
        # to find out who has an account.
        raise UnauthorizedError("Incorrect email or password.")
    limits.login_succeeded(email)
    _set_session_cookie(response, user.id, user.token_version, settings, versions)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, settings: SettingsDep) -> None:
    """Remove the session cookie. Works even if the session has already expired."""
    _clear_session_cookie(response, settings)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    """The signed-in user, with their preferences. The frontend calls this on load to know
    whether you're signed in."""
    return user


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, user_id: CurrentUserId, db: DbSession):
    """Change your name and/or preferences (only the fields sent). The email can't change."""
    preferences = body.preferences.model_dump(exclude_unset=True) if body.preferences else None
    return service.update_profile(db, user_id, full_name=body.full_name, preferences=preferences)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: PasswordChange,
    response: Response,
    user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
    limits: LimitsDep,
    address: ClientAddress,
    versions: TokenVersionsDep,
) -> None:
    """Change your password. Every other session ends (their tokens carry the old version);
    this browser gets a new cookie. A wrong current password is 400 (not 401, which would mean
    "signed out") and counts as a failed sign-in for your email."""
    limits.check_login(user.email, address)
    version = service.change_password(
        db, user.id, current=body.current_password, new=body.new_password
    )
    if version is None:
        limits.login_failed(user.email, address)
        raise AppError(service.WRONG_PASSWORD)
    _set_session_cookie(response, user.id, version, settings, versions)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_everywhere(
    response: Response,
    user_id: CurrentUserId,
    db: DbSession,
    settings: SettingsDep,
    versions: TokenVersionsDep,
) -> None:
    """Sign out on every device, this one included (e.g. after using a shared computer)."""
    version = service.bump_token_version(db, user_id)
    db.commit()
    versions.set(user_id, version)
    _clear_session_cookie(response, settings)
