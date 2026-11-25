"""Request and response bodies for /api/auth/*."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.search import TOP_K_MAX

# NIST SP 800-63B: at least 8 characters, no composition rules ("one symbol..."), long passphrases
# welcome. The upper bound stops someone sending megabytes to the (deliberately slow) hasher.
PASSWORD_MIN = 8
PASSWORD_MAX = 128


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)
    full_name: str = Field(min_length=1, max_length=200)

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Enter your name")
        return v.strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=PASSWORD_MAX)


class Preferences(BaseModel):
    """Per-user defaults (M16), kept in `users.settings`. The Search page starts from the search
    ones; the chat sends `chat_multi_query` with each question (no extra query per question).
    Unknown stored keys are ignored, so a removed preference can't break reading a user."""

    model_config = ConfigDict(extra="ignore")

    search_mode: Literal["semantic", "keyword", "hybrid"] = "hybrid"
    search_top_k: int = Field(default=10, ge=1, le=TOP_K_MAX)
    search_min_score: float | None = Field(default=None, ge=0, le=1)
    # Extra phrasings (D75): one planning call per question. Off saves one Gemini call.
    chat_multi_query: bool = True


class PreferencesUpdate(BaseModel):
    """Only the fields sent change; `search_min_score: null` clears the minimum."""

    model_config = ConfigDict(extra="forbid")

    search_mode: Literal["semantic", "keyword", "hybrid"] | None = None
    search_top_k: int | None = Field(default=None, ge=1, le=TOP_K_MAX)
    search_min_score: float | None = Field(default=None, ge=0, le=1)
    chat_multi_query: bool | None = None


class ProfileUpdate(BaseModel):
    """PATCH /api/auth/me. The email can't be changed here (it is the sign-in name)."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    preferences: PreferencesUpdate | None = None

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Enter your name")
        return v.strip() if v is not None else None


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=PASSWORD_MAX)
    new_password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)


class UserOut(BaseModel):
    """What the API reveals about a user. Never the password hash or the token version."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    created_at: datetime
    preferences: Preferences
