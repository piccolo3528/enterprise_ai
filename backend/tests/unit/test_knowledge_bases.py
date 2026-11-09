"""Knowledge base rules that need no database: input cleaning, PATCH semantics, route guards."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from app.core.security import SESSION_COOKIE, create_access_token
from app.models import KnowledgeBase
from app.schemas.knowledge_base import (
    DESCRIPTION_MAX,
    NAME_MAX,
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
)
from tests.helpers import FAKE_JWT_SECRET

# --- names and descriptions -------------------------------------------------------------------


def test_name_is_trimmed_and_inner_whitespace_collapsed():
    assert KnowledgeBaseCreate(name="  HR \t  policies\n").name == "HR policies"


@pytest.mark.parametrize("name", ["", "   ", "\n\t"])
def test_blank_names_are_rejected(name):
    with pytest.raises(ValidationError, match="Enter a name"):
        KnowledgeBaseCreate(name=name)


@pytest.mark.parametrize("name", ["bad\x00name", "bell\x07", "esc\x1b[31m"])
def test_control_characters_are_rejected(name):
    # NUL would otherwise reach PostgreSQL, which refuses it in text columns: a 500, not a 422.
    with pytest.raises(ValidationError, match="characters that aren't allowed"):
        KnowledgeBaseCreate(name=name)


def test_name_length_is_checked_after_cleaning():
    assert len(KnowledgeBaseCreate(name="x" * NAME_MAX + "   ").name) == NAME_MAX
    with pytest.raises(ValidationError, match=f"at most {NAME_MAX}"):
        KnowledgeBaseCreate(name="x" * (NAME_MAX + 1))


def test_unicode_names_are_fine():
    name = "Política de RRHH — 2026 📚"
    assert KnowledgeBaseCreate(name=name).name == name


def test_description_keeps_line_breaks_and_empty_means_none():
    body = KnowledgeBaseCreate(name="HR", description="  Line one\n\tLine two  ")
    assert body.description == "Line one\n\tLine two"
    assert KnowledgeBaseCreate(name="HR", description="   ").description is None
    with pytest.raises(ValidationError, match=f"at most {DESCRIPTION_MAX}"):
        KnowledgeBaseCreate(name="HR", description="d" * (DESCRIPTION_MAX + 1))
    with pytest.raises(ValidationError, match="characters that aren't allowed"):
        KnowledgeBaseCreate(name="HR", description="nul\x00")


# --- PATCH semantics ----------------------------------------------------------------------------


def test_patch_changes_only_the_fields_sent():
    assert KnowledgeBaseUpdate(name=" New ").changes() == {"name": "New"}
    assert KnowledgeBaseUpdate(description="About").changes() == {"description": "About"}


def test_patch_with_null_description_clears_it():
    assert KnowledgeBaseUpdate.model_validate({"description": None}).changes() == {
        "description": None
    }


def test_patch_cannot_remove_the_name():
    with pytest.raises(ValidationError, match="must have a name"):
        KnowledgeBaseUpdate.model_validate({"name": None})


def test_empty_patch_is_rejected():
    with pytest.raises(ValidationError, match="Send a name or a description"):
        KnowledgeBaseUpdate.model_validate({})


# --- schema ---------------------------------------------------------------------------------------


def test_names_are_unique_per_owner_ignoring_case():
    (index,) = KnowledgeBase.__table__.indexes
    sql = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert sql == (
        "CREATE UNIQUE INDEX uq_knowledge_bases_owner_id_lower_name "
        "ON knowledge_bases (owner_id, lower(name))"
    )


# --- route guards (no database: they answer before any query) -----------------------------------

KB_URL = f"/api/knowledge-bases/{uuid.uuid4()}"


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("get", "/api/knowledge-bases"),
        ("post", "/api/knowledge-bases"),
        ("get", KB_URL),
        ("patch", KB_URL),
        ("delete", KB_URL),
        ("get", "/api/knowledge-bases/not-a-uuid"),  # 401 comes before the id is looked at
    ],
)
def test_every_endpoint_needs_a_session(client, method, url):
    response = client.request(method, url, json={"name": "x"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "123", "00000000-0000-0000-0000"])
def test_a_malformed_id_is_not_found_not_a_validation_error(client, bad_id):
    token = create_access_token(uuid.uuid4(), FAKE_JWT_SECRET, 5)
    client.cookies.set(SESSION_COOKIE, token)
    response = client.get(f"/api/knowledge-bases/{bad_id}")
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Knowledge base not found."
