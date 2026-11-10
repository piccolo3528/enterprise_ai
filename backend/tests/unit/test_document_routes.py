"""Document route guards that answer before any database or disk work."""

from __future__ import annotations

import uuid

import pytest

from app.core.security import SESSION_COOKIE, create_access_token
from tests.helpers import FAKE_JWT_SECRET

KB = f"/api/knowledge-bases/{uuid.uuid4()}/documents"
DOC = f"/api/documents/{uuid.uuid4()}"


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("post", KB),
        ("get", KB),
        ("get", DOC),
        ("get", f"{DOC}/chunks"),
        ("delete", DOC),
        ("post", f"{DOC}/reprocess"),
    ],
)
def test_every_document_endpoint_needs_a_session(client, method, url):
    response = client.request(method, url, files={"file": ("a.txt", b"hello")})
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "suffix"),
    [("get", ""), ("get", "/chunks"), ("delete", ""), ("post", "/reprocess")],
)
def test_a_malformed_document_id_is_not_found(client, method, suffix):
    client.cookies.set(SESSION_COOKIE, create_access_token(uuid.uuid4(), FAKE_JWT_SECRET, 5))
    response = client.request(method, f"/api/documents/not-a-uuid{suffix}")
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Document not found."
