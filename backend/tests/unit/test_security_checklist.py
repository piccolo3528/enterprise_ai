"""The M16 security checklist as tests (ARCHITECTURE §4.16). No network: the database and Qdrant
URLs point at closed local ports, so anything that reaches them fails for real.

The cross-user part of the authorization matrix (user B with user A's real ids) needs the
database: tests/integration/test_authz_matrix.py.
"""

from __future__ import annotations

import io
import logging
import struct
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.core.config import ConfigError
from app.core.security import SESSION_COOKIE, create_access_token
from app.factory import create_app
from app.services.ingestion.validation import check_content
from tests.helpers import FAKE_DB_PASSWORD, FAKE_JWT_SECRET, make_settings

# --- 1. authorization on every route -------------------------------------------------------------
#
# Every route the API serves, and who may call it. A route added without a line here fails
# test_every_route_is_classified, so nobody can add an endpoint and forget to decide.
#   public: no session needed     self: acts only on the session's own user
#   owned:  acts on the ids in the path, which must belong to the session's user (404 otherwise)

ROUTES = {
    ("GET", "/api/health"): "public",  # signed out: {"status": "ok"} only
    ("POST", "/api/auth/register"): "public",
    ("POST", "/api/auth/login"): "public",
    ("POST", "/api/auth/logout"): "public",
    ("GET", "/api/auth/me"): "self",
    ("PATCH", "/api/auth/me"): "self",
    ("POST", "/api/auth/password"): "self",
    ("POST", "/api/auth/logout-all"): "self",
    ("GET", "/api/stats"): "self",
    ("GET", "/api/knowledge-bases"): "self",
    ("POST", "/api/knowledge-bases"): "self",
    ("GET", "/api/knowledge-bases/{kb_id}"): "owned",
    ("PATCH", "/api/knowledge-bases/{kb_id}"): "owned",
    ("DELETE", "/api/knowledge-bases/{kb_id}"): "owned",
    ("POST", "/api/knowledge-bases/{kb_id}/documents"): "owned",
    ("GET", "/api/knowledge-bases/{kb_id}/documents"): "owned",
    ("GET", "/api/documents/{document_id}"): "owned",
    ("DELETE", "/api/documents/{document_id}"): "owned",
    ("GET", "/api/documents/{document_id}/chunks"): "owned",
    ("POST", "/api/documents/{document_id}/reprocess"): "owned",
    ("POST", "/api/knowledge-bases/{kb_id}/search"): "owned",
    ("POST", "/api/knowledge-bases/{kb_id}/ask"): "owned",
    ("POST", "/api/knowledge-bases/{kb_id}/conversations"): "owned",
    ("GET", "/api/knowledge-bases/{kb_id}/conversations"): "owned",
    ("POST", "/api/conversations/{conversation_id}/messages"): "owned",
    ("GET", "/api/conversations/{conversation_id}"): "owned",
    ("PATCH", "/api/conversations/{conversation_id}"): "owned",
    ("DELETE", "/api/conversations/{conversation_id}"): "owned",
}

# Valid bodies, so a 401/404 can't be a 422 in disguise.
BODIES = {
    ("PATCH", "/api/auth/me"): {"full_name": "X"},
    ("POST", "/api/auth/password"): {"current_password": "a", "new_password": "long-enough"},
    ("POST", "/api/knowledge-bases"): {"name": "KB"},
    ("PATCH", "/api/knowledge-bases/{kb_id}"): {"name": "KB"},
    ("POST", "/api/knowledge-bases/{kb_id}/search"): {"query": "leave"},
    ("POST", "/api/knowledge-bases/{kb_id}/ask"): {"question": "How many days?"},
    ("POST", "/api/knowledge-bases/{kb_id}/conversations"): {"question": "How many days?"},
    ("POST", "/api/conversations/{conversation_id}/messages"): {"question": "And then?"},
    ("PATCH", "/api/conversations/{conversation_id}"): {"title": "T"},
}


def fill(path: str, value: str) -> str:
    for name in ("{kb_id}", "{document_id}", "{conversation_id}"):
        path = path.replace(name, value)
    return path


def call(client, method, path, value=None):
    url = fill(path, value or str(uuid.uuid4()))
    return client.request(method, url, json=BODIES.get((method, path)))


@pytest.fixture
def client():
    with TestClient(create_app(make_settings(), warm_up=False), base_url="https://testserver") as c:
        yield c


def test_every_route_is_classified(client):
    served = {
        (method.upper(), path)
        for path, item in client.app.openapi()["paths"].items()
        for method in item
    }
    assert served == set(ROUTES), (
        f"unclassified: {served - set(ROUTES)}; gone: {set(ROUTES) - served}"
    )


@pytest.mark.parametrize(("method", "path"), [r for r, kind in ROUTES.items() if kind != "public"])
@pytest.mark.parametrize("cookie", [None, "garbage", "expired"])
def test_every_non_public_route_needs_a_valid_session(client, method, path, cookie):
    client.cookies.clear()
    if cookie == "garbage":
        client.cookies.set(SESSION_COOKIE, "not.a.jwt")
    elif cookie == "expired":
        client.cookies.set(SESSION_COOKIE, create_access_token(uuid.uuid4(), FAKE_JWT_SECRET, -1))
    response = call(client, method, path)
    assert response.status_code == 401, (method, path, response.text)
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(("method", "path"), [r for r, kind in ROUTES.items() if kind == "owned"])
def test_a_malformed_id_is_404_like_someone_elses(client, method, path):
    client.cookies.set(SESSION_COOKIE, create_access_token(uuid.uuid4(), FAKE_JWT_SECRET, 5))
    response = call(client, method, path, value="1 OR 1=1")
    assert response.status_code == 404, (method, path, response.text)
    assert response.json()["error"]["code"] == "not_found"


def test_a_token_signed_with_another_key_is_refused(client):
    client.cookies.set(SESSION_COOKIE, create_access_token(uuid.uuid4(), "x" * 40, 5))
    assert client.get("/api/auth/me").status_code == 401


# --- 2. headers, docs ----------------------------------------------------------------------------


@pytest.mark.parametrize("url", ["/api/health", "/api/auth/me", "/api/no-such-route"])
def test_api_responses_carry_the_security_headers_even_on_errors(client, url):
    response = client.get(url)
    assert response.headers["x-content-type-options"] == "nosniff"
    csp = "default-src 'none'; frame-ancestors 'none'"
    assert response.headers["content-security-policy"] == csp
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_the_docs_page_keeps_working_without_the_api_csp(client):
    response = client.get("/docs")
    assert response.status_code == 200 and "content-security-policy" not in response.headers


def test_the_api_docs_can_be_turned_off():
    with TestClient(create_app(make_settings(api_docs_enabled=False), warm_up=False)) as c:
        assert [c.get(u).status_code for u in ("/docs", "/redoc", "/openapi.json")] == [404] * 3


# --- 3. secrets never in logs or responses -------------------------------------------------------

SECRETS = {
    "database password": FAKE_DB_PASSWORD,
    "JWT secret": FAKE_JWT_SECRET,
    "Gemini key": "fake-gemini-key-for-the-secrets-test",
    "Groq key": "gsk_fake_groq_key_for_tests",
    "Qdrant key": "fake-qdrant-key-for-tests",
    "a user's password": "users-own-password-123",
}


@pytest.mark.filterwarnings("ignore:Api key is used with an insecure connection")  # local fake
def test_secrets_appear_in_no_log_line_and_no_response(caplog):
    caplog.set_level(logging.DEBUG)
    settings = make_settings(
        gemini_api_key=SECRETS["Gemini key"],
        groq_api_key=SECRETS["Groq key"],
        qdrant_api_key=SECRETS["Qdrant key"],
    )
    responses = []
    with TestClient(create_app(settings, warm_up=False), base_url="https://testserver") as c:
        password = SECRETS["a user's password"]
        # A validation error, a sign-in that fails inside the database driver (500 with a
        # traceback in the log), a signed-in health check whose database and Qdrant calls fail.
        responses.append(c.post("/api/auth/register", json={"email": "bad", "password": password}))
        responses.append(c.post("/api/auth/login", json={"email": "a@example.com",
                                                          "password": password}))  # fmt: skip
        token = create_access_token(uuid.uuid4(), FAKE_JWT_SECRET, 5)
        c.cookies.set(SESSION_COOKIE, token)
        responses.append(c.get("/api/health"))
    assert responses[1].status_code == 500  # the database really was unreachable
    assert responses[2].json()["services"]["database"]["status"] == "error"
    logs = caplog.text + "".join(r.getMessage() for r in caplog.records)
    for name, value in {**SECRETS, "session token": token}.items():
        assert value not in logs, f"{name} in the log"
        for response in responses:
            assert value not in response.text, f"{name} in a response"
    assert "qdrant_api_key': 'set'" in logs  # the startup line says *whether* it's set


def test_a_qdrant_key_is_refused_over_plain_http_to_another_host():
    with pytest.raises(ConfigError, match="https"):
        make_settings(qdrant_url="http://qdrant.example.com:6333", qdrant_api_key="k")
    make_settings(qdrant_url="http://127.0.0.1:6333", qdrant_api_key="k")  # local: allowed
    make_settings(qdrant_url="https://qdrant.example.com", qdrant_api_key="k")


def test_the_health_report_never_names_the_qdrant_host(client, monkeypatch):
    from app.services import health

    monkeypatch.setattr(health.db_session, "ping", lambda engine: 1)
    client.cookies.set(SESSION_COOKIE, create_access_token(uuid.uuid4(), FAKE_JWT_SECRET, 5))
    text = client.get("/api/health").text
    assert "6999" not in text and "127.0.0.1" not in text and "qdrant_url" not in text


# --- 4. upload abuse -----------------------------------------------------------------------------


def test_a_docx_that_lies_about_its_unpacked_size_is_refused_without_unpacking(tmp_path):
    # 50 MB of text that compresses to ~49 KB, with headers claiming 1,000 bytes: the archive
    # check trusts the declared sizes, and Python's zipfile stops reading at the declared size
    # (CRC mismatch), so the real 50 MB is never produced. Measured in M16.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", b"A" * 50_000_000)
    data = bytearray(buffer.getvalue())
    # The name follows its local header (30 bytes) and its central-directory entry (46 bytes);
    # the uncompressed size sits at offset 22 and 24 of those.
    name = b"word/document.xml"
    local = data.find(name) - 30
    central = data.find(name, local + 31) - 46
    assert data[local : local + 4] == b"PK\x03\x04" and data[central : central + 4] == b"PK\x01\x02"
    struct.pack_into("<I", data, local + 22, 1000)
    struct.pack_into("<I", data, central + 24, 1000)
    path = tmp_path / "lying.docx"
    path.write_bytes(bytes(data))
    assert len(data) < 100_000
    with zipfile.ZipFile(path) as archive, pytest.raises(zipfile.BadZipFile):
        archive.read("word/document.xml")
    check_content(path, "docx")  # passes the size check (declared 1 KB)...
    from app.services.ingestion.extractors import ExtractionError, extract

    with pytest.raises(ExtractionError):  # ...and fails as damaged when read, after 1 KB
        extract(path, "docx")
