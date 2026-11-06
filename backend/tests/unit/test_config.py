from __future__ import annotations

import pytest
from conftest import BASE_VALUES, FAKE_DB_PASSWORD, FAKE_JWT_SECRET, make_settings

from app.core.config import BACKEND_DIR, ConfigError, load_settings


def test_valid_settings_load(settings):
    assert settings.database_url.get_secret_value() == BASE_VALUES["database_url"]
    assert settings.qdrant_collection == "chunks"
    assert settings.log_level == "INFO"


def test_secrets_are_masked_when_printed(settings):
    for text in (repr(settings), str(settings), str(settings.describe())):
        assert FAKE_DB_PASSWORD not in text
        assert FAKE_JWT_SECRET not in text
        assert "fake-gemini-key" not in text


def test_describe_reports_only_whether_secrets_are_set(settings):
    summary = settings.describe()
    assert summary["database_url"] == "set"
    assert summary["groq_api_key"] == "not set"


def test_missing_required_secrets_give_a_clear_error():
    with pytest.raises(ConfigError) as exc_info:
        load_settings(_env_file=None)
    message = str(exc_info.value)
    assert "DATABASE_URL: is required but not set" in message
    assert "JWT_SECRET: is required but not set" in message


def test_placeholder_database_url_is_rejected():
    template = "postgresql+psycopg://USER:PASSWORD@ep-xxxx-pooler.REGION.aws.neon.tech/DATABASE"
    with pytest.raises(ConfigError, match="placeholder"):
        make_settings(database_url=template)


def test_bad_url_error_never_contains_the_password():
    secret_url = "postgresql://admin:Sup3rS3cret!@db.example.com/app"  # missing +psycopg
    with pytest.raises(ConfigError) as exc_info:
        make_settings(database_url=secret_url)
    err = exc_info.value
    assert "postgresql+psycopg://" in str(err)
    assert "Sup3rS3cret" not in str(err)
    # `raise ... from None` drops pydantic's original error, whose text echoes the input.
    assert err.__cause__ is None and err.__suppress_context__


def test_short_jwt_secret_is_rejected():
    with pytest.raises(ConfigError, match="JWT_SECRET: must be at least 32 characters"):
        make_settings(jwt_secret="too-short")


def test_overlap_must_be_smaller_than_chunk_size():
    with pytest.raises(ConfigError, match="CHUNK_OVERLAP_TOKENS must be smaller"):
        make_settings(chunk_size_tokens=100, chunk_overlap_tokens=100)


def test_rerank_top_n_cannot_exceed_top_k():
    with pytest.raises(ConfigError, match="RERANK_TOP_N"):
        make_settings(retrieval_top_k=5, rerank_top_n=10)


def test_empty_environment_value_means_not_set(monkeypatch):
    monkeypatch.setenv("QDRANT_API_KEY", "")  # like the line `QDRANT_API_KEY=` in .env
    assert make_settings().qdrant_api_key is None


def test_untouched_optional_url_template_counts_as_not_set():
    template = "postgresql+psycopg://USER:PASSWORD@ep-yyyy-pooler.REGION.aws.neon.tech/DATABASE"
    assert make_settings(test_database_url=template).test_database_url is None


def test_relative_upload_dir_is_resolved_from_backend_folder():
    settings = make_settings(upload_dir="./storage/uploads")
    assert settings.upload_dir == (BACKEND_DIR / "storage" / "uploads").resolve()


def test_log_level_is_case_insensitive_and_validated():
    assert make_settings(log_level="debug").log_level == "DEBUG"
    with pytest.raises(ConfigError, match="LOG_LEVEL"):
        make_settings(log_level="verbose")
