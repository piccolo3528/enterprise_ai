"""Every setting the backend reads, in one typed, validated place (ARCHITECTURE section 8).

Values come from environment variables, then from backend/.env. Secrets are `SecretStr`, so
printing or logging the settings object shows `**********` instead of the value. Call
`secret.get_secret_value()` only at the point where the real value is needed (e.g. creating the
database engine).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Template values from .env.example. A URL containing one of these was never filled in.
_PLACEHOLDER_MARKERS = ("USER:PASSWORD", "ep-xxxx", "ep-yyyy")


class ConfigError(RuntimeError):
    """Raised when the configuration is missing or invalid. The message never contains values."""


def _is_placeholder(url: str) -> bool:
    return any(marker in url for marker in _PLACEHOLDER_MARKERS)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Absolute path, so it works whatever folder uvicorn/pytest is started from.
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,  # `QDRANT_API_KEY=` means "not set", not "empty string"
        extra="ignore",  # .env may hold variables used by scripts only
    )

    log_level: str = "INFO"

    # --- PostgreSQL (Neon) -----------------------------------------------------------
    database_url: SecretStr  # pooled; the URL embeds the password, so the whole URL is secret
    database_migration_url: SecretStr | None = None  # direct; Alembic only (M4)
    test_database_url: SecretStr | None = None  # Neon "test" branch (M4)

    # --- Qdrant -----------------------------------------------------------------------
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "chunks"

    # --- LLM ----------------------------------------------------------------------------
    gemini_api_key: SecretStr | None = None  # required from M12, when answers are generated
    gemini_model_answer: str = "gemini-3.5-flash-lite"
    gemini_model_utility: str = "gemini-3.5-flash-lite"
    gemini_rpm_limit: int = Field(default=10, ge=1)
    groq_api_key: SecretStr | None = None  # optional fallback provider (D22), not wired in
    groq_model: str | None = None

    # --- Local models -------------------------------------------------------------------
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # --- Auth ---------------------------------------------------------------------------
    jwt_secret: SecretStr
    jwt_expire_minutes: int = Field(default=60, ge=1)

    # --- Uploads ------------------------------------------------------------------------
    upload_dir: Path = Path("./storage/uploads")
    max_upload_mb: int = Field(default=20, ge=1)

    # --- RAG tuning ---------------------------------------------------------------------
    chunk_size_tokens: int = Field(default=400, ge=50)
    chunk_overlap_tokens: int = Field(default=60, ge=0)
    retrieval_top_k: int = Field(default=20, ge=1)
    rerank_top_n: int = Field(default=5, ge=1)
    context_token_budget: int = Field(default=5000, ge=500)

    # ------------------------------------------------------------------------- validators
    # Error messages describe the problem without echoing the value (it may hold a password).
    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls, v: SecretStr) -> SecretStr:
        url = v.get_secret_value()
        if _is_placeholder(url):
            raise ValueError("still contains the .env.example placeholder; paste your Neon URL")
        if not url.startswith("postgresql+psycopg://"):
            raise ValueError(
                "must start with 'postgresql+psycopg://' (selects the psycopg 3 driver)"
            )
        return v

    @field_validator("database_migration_url", "test_database_url")
    @classmethod
    def _optional_url_placeholder_is_unset(cls, v: SecretStr | None) -> SecretStr | None:
        # These aren't needed until M4; an untouched template line simply means "not set yet".
        if v is not None and _is_placeholder(v.get_secret_value()):
            return None
        return v

    @field_validator("jwt_secret")
    @classmethod
    def _check_jwt_secret(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError("must be at least 32 characters; see .env.example for a generator")
        return v

    @field_validator("log_level")
    @classmethod
    def _check_log_level(cls, v: str) -> str:
        level = v.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError("must be DEBUG, INFO, WARNING or ERROR")
        return level

    @field_validator("upload_dir")
    @classmethod
    def _resolve_upload_dir(cls, v: Path) -> Path:
        return v if v.is_absolute() else (BACKEND_DIR / v).resolve()

    @model_validator(mode="after")
    def _check_rag_numbers(self) -> Settings:
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_SIZE_TOKENS")
        if self.rerank_top_n > self.retrieval_top_k:
            raise ValueError("RERANK_TOP_N cannot be larger than RETRIEVAL_TOP_K")
        return self

    # ------------------------------------------------------------------------- helpers
    def describe(self) -> dict[str, str]:
        """Safe startup summary: which secrets are set, never their values."""

        def is_set(secret: SecretStr | None) -> str:
            return "set" if secret is not None else "not set"

        return {
            "database_url": is_set(self.database_url),
            "database_migration_url": is_set(self.database_migration_url),
            "qdrant_api_key": is_set(self.qdrant_api_key),
            "gemini_api_key": is_set(self.gemini_api_key),
            "groq_api_key": is_set(self.groq_api_key),
            "jwt_secret": is_set(self.jwt_secret),
            "gemini_model_answer": self.gemini_model_answer,
            "embedding_model": self.embedding_model,
        }


def load_settings(**overrides) -> Settings:
    """Build Settings, turning pydantic's ValidationError into a ConfigError.

    pydantic's own error text includes `input_value=...`, which for a bad DATABASE_URL would
    print the password into the terminal. We rebuild the message from field names and our own
    descriptions only.
    """
    try:
        return Settings(**overrides)
    except ValidationError as exc:
        problems = []
        for err in exc.errors(include_input=False, include_url=False):
            field = ".".join(str(part) for part in err["loc"]).upper() or "settings"
            message = err["msg"].removeprefix("Value error, ")
            if err["type"] == "missing":
                message = "is required but not set (add it to backend/.env)"
            problems.append(f"  - {field}: {message}")
        raise ConfigError("Invalid configuration:\n" + "\n".join(problems)) from None


@lru_cache
def get_settings() -> Settings:
    """The process-wide settings, loaded once."""
    return load_settings()
