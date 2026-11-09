"""Request and response bodies for /api/auth/*."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

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


class UserOut(BaseModel):
    """What the API reveals about a user. Never the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    created_at: datetime
