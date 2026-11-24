"""Every setting the backend reads, in one typed, validated place (ARCHITECTURE section 8).

Values come from environment variables, then from backend/.env. Secrets are `SecretStr`, so
printing or logging the settings object shows `**********` instead of the value. Call
`secret.get_secret_value()` only at the point where the real value is needed (e.g. creating the
database engine).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Template values from .env.example. A URL containing one of these was never filled in.
_PLACEHOLDER_MARKERS = ("USER:PASSWORD", "ep-xxxx", "ep-yyyy")


class ConfigError(RuntimeError):
    """Raised when the configuration is missing or invalid. The message never contains values."""


def _is_placeholder(url: str) -> bool:
    return any(marker in url for marker in _PLACEHOLDER_MARKERS)


def _require_psycopg_driver(url: str) -> None:
    # Neon's console shows "postgresql://", which makes SQLAlchemy look for the old psycopg2
    # driver (not installed) and fail with a confusing import error at the first query.
    if not url.startswith("postgresql+psycopg://"):
        raise ValueError("must start with 'postgresql+psycopg://' (selects the psycopg 3 driver)")


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
    # Fallback chain (M15, D80): another Gemini model on the same key (its own free daily quota),
    # then Groq. Empty = skip that step.
    # Measured 2026-11-23: gemini-3.5-flash allowed only ~20-30 free calls a day and took
    # 10-24 s per call; gemini-3.1-flash-lite answered in ~2 s (D80).
    gemini_model_fallback: str | None = "gemini-3.1-flash-lite"
    # The answer judge of evaluation/run_answers.py (D81): Groq by default, a different company
    # and model family from the Gemini models that answer; "gemini" uses GEMINI_MODEL_JUDGE.
    judge_provider: Literal["groq", "gemini"] = "groq"
    gemini_model_judge: str = "gemini-3.1-flash-lite"
    gemini_rpm_limit: int = Field(default=10, ge=1)
    # Generation (M12). Low temperature: factual Q&A favours repeatable answers (§4.6).
    llm_temperature: float = Field(default=0.1, ge=0, le=2)
    llm_max_output_tokens: int = Field(default=1024, ge=64, le=8192)
    llm_timeout_seconds: float = Field(default=25, gt=0, le=120)  # per attempt
    llm_max_retries: int = Field(default=2, ge=0, le=5)  # on 429 (per-minute), 5xx, timeouts
    groq_api_key: SecretStr | None = None  # last step of the fallback chain (D22, wired in M15)
    groq_model: str = "openai/gpt-oss-120b"
    groq_rpm_limit: int = Field(default=30, ge=1)  # free tier: 1,000/day, 8,000 tokens/minute

    # --- Local models -------------------------------------------------------------------
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # --- Auth ---------------------------------------------------------------------------
    jwt_secret: SecretStr
    jwt_expire_minutes: int = Field(default=60, ge=1)
    # Secure cookies are only sent over HTTPS. Browsers treat http://localhost as secure, so this
    # stays True in development too; only set it False for plain-HTTP hosts other than localhost.
    cookie_secure: bool = True

    # --- Uploads ------------------------------------------------------------------------
    upload_dir: Path = Path("./storage/uploads")
    max_upload_mb: int = Field(default=20, ge=1)

    # --- RAG tuning ---------------------------------------------------------------------
    # Counted in embedding-model tokens; 510 = the model's 512 minus its two special tokens.
    chunk_size_tokens: int = Field(default=400, ge=50, le=510)
    chunk_overlap_tokens: int = Field(default=60, ge=0)
    # auto = heading-aware when the document has headings (Markdown, DOCX), else recursive.
    chunk_strategy: Literal["auto", "fixed", "overlap", "recursive", "heading"] = "auto"
    retrieval_top_k: int = Field(default=20, ge=1)
    context_token_budget: int = Field(default=5000, ge=500)
    # Passages given to the LLM (M12): hybrid Hit@10 100 % vs Hit@5 96 %, Recall@10 90 % vs
    # 83 %, for ~2.7k tokens (M11 baseline). The token budget above still caps the total.
    context_max_sources: int = Field(default=10, ge=1, le=50)
    # Conversation memory (M13): the most recent turns (question + answer) given to the
    # follow-up rewriter, trimmed oldest first to the token budget. History never goes into the
    # answer prompt (D69).
    history_max_turns: int = Field(default=6, ge=1, le=50)
    history_token_budget: int = Field(default=1500, ge=100)
    # Retrieval techniques (M14), each measured in evaluation/compare_retrieval.py before its
    # default was chosen (PROJECT_TRACKER D72-D76).
    rerank_enabled: bool = False  # cross-encoder over the hybrid pool
    rerank_pool: int = Field(default=20, ge=1, le=100)  # hybrid results the cross-encoder reads
    rerank_min_score: float | None = None  # drop passages scored below this (logit)
    version_mode: Literal["off", "demote", "filter"] = "demote"  # outdated versions (S4)
    amendments_enabled: bool = False  # fetch amendments with their base document (S4)
    multi_query_enabled: bool = True  # extra phrasings in the planning call (D75)

    # ------------------------------------------------------------------------- validators
    # Error messages describe the problem without echoing the value (it may hold a password).
    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls, v: SecretStr) -> SecretStr:
        url = v.get_secret_value()
        if _is_placeholder(url):
            raise ValueError("still contains the .env.example placeholder; paste your Neon URL")
        _require_psycopg_driver(url)
        return v

    @field_validator("database_migration_url", "test_database_url")
    @classmethod
    def _check_optional_url(cls, v: SecretStr | None) -> SecretStr | None:
        # An untouched template line simply means "not set yet".
        if v is None or _is_placeholder(v.get_secret_value()):
            return None
        _require_psycopg_driver(v.get_secret_value())
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
