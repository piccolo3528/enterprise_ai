"""Documents end to end: upload, processing (extraction + chunking), listing, chunks, deletion
and reprocessing. Real PostgreSQL (Neon test branch, rolled back), real parsers, real tokenizer,
files in a temporary folder.

Starlette's TestClient runs background tasks before `client.post(...)` returns, so a test sees
the finished status straight after the upload.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_db, get_read_db, get_session_factory
from app.core.config import load_settings
from app.factory import create_app
from app.models import Chunk, Document
from app.services.ingestion.extractors import NO_TEXT
from app.services.ingestion.pipeline import (
    INTERRUPTED,
    ChunkingConfig,
    process_document,
    recover_interrupted,
)
from app.services.storage import Storage
from tests import sample_files
from tests.helpers import act_as, save

pytestmark = pytest.mark.live

MAX_MB = 1  # a small limit, so "too large" needs only ~1 MB


@pytest.fixture
def uploads(tmp_path):
    return tmp_path / "uploads"


@pytest.fixture
def client(db, uploads):
    settings = load_settings(upload_dir=uploads, max_upload_mb=MAX_MB)
    app = create_app(settings, warm_up=False)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_read_db] = lambda: db

    @contextmanager
    def shared_session():  # the background job uses the test's rolled-back session too
        yield db

    app.dependency_overrides[get_session_factory] = lambda: shared_session
    with TestClient(app, base_url="https://testserver") as c:
        c.secret = settings.jwt_secret.get_secret_value()
        yield c


def new_kb(client, name=None) -> str:
    response = client.post("/api/knowledge-bases", json={"name": name or uuid.uuid4().hex[:8]})
    assert response.status_code == 201
    return response.json()["id"]


def upload(client, kb_id, filename, data: bytes):
    return client.post(f"/api/knowledge-bases/{kb_id}/documents", files={"file": (filename, data)})


def documents(client, kb_id):
    return client.get(f"/api/knowledge-bases/{kb_id}/documents").json()["items"]


def stored_files(uploads):
    return sorted(p.name for p in uploads.rglob("*") if p.is_file()) if uploads.exists() else []


# --- the happy path, one per format --------------------------------------------------------------


def test_markdown_upload_is_accepted_then_processed(client, alice, uploads):
    act_as(client, alice)
    kb_id = new_kb(client)
    response = upload(
        client, kb_id, "C:\\Users\\alice\\leave policy.md", sample_files.MARKDOWN.encode()
    )
    assert response.status_code == 202
    accepted = response.json()
    assert accepted["status"] == "uploaded"  # the answer is sent before processing starts
    assert accepted["original_filename"] == "leave policy.md"  # path stripped
    assert "stored_path" not in accepted

    (document,) = documents(client, kb_id)
    assert document["status"] == "ready"
    assert document["error_message"] is None
    assert document["metadata"]["document_id"] == "NX-HR-002"
    assert document["metadata"]["status"] == "current"
    assert document["processed_at"] is not None
    # Stored under a server-chosen name, not the user's.
    assert stored_files(uploads) == [f"{document['id']}.md"]
    assert (uploads / kb_id / f"{document['id']}.md").exists()
    assert client.get(f"/api/knowledge-bases/{kb_id}").json()["document_count"] == 1


@pytest.mark.parametrize(
    ("filename", "data", "pages"),
    [
        ("leave.pdf", sample_files.pdf("Annual leave is 24 days.", "Sick leave is 10 days."), 2),
        ("leave.docx", sample_files.docx(("h1", "Leave"), ("p", "Annual leave is 24 days.")), None),
        ("leave.txt", "Annual leave is 24 days.".encode("cp1252"), None),
    ],
)
def test_every_format_reaches_ready(client, alice, filename, data, pages):
    act_as(client, alice)
    kb_id = new_kb(client)
    assert upload(client, kb_id, filename, data).status_code == 202
    (document,) = documents(client, kb_id)
    assert (document["status"], document["page_count"], document["error_message"]) == (
        "ready",
        pages,
        None,
    )


# --- files that are accepted but can't be processed -> failed, with a reason -----------------


@pytest.mark.parametrize(
    ("filename", "data", "message"),
    [
        ("scan.pdf", sample_files.pdf("", ""), NO_TEXT),
        ("locked.pdf", sample_files.pdf("secret", password="pw-123"), "password-protected"),
        ("blank.txt", b"   \n\n  ", "No text could be found"),
    ],
)
def test_unprocessable_files_fail_with_a_readable_reason(client, alice, filename, data, message):
    act_as(client, alice)
    kb_id = new_kb(client)
    assert upload(client, kb_id, filename, data).status_code == 202
    (document,) = documents(client, kb_id)
    assert document["status"] == "failed"
    assert message in document["error_message"]


def test_a_failed_document_can_be_reprocessed(client, alice):
    act_as(client, alice)
    kb_id = new_kb(client)
    upload(client, kb_id, "scan.pdf", sample_files.pdf(""))
    (failed,) = documents(client, kb_id)

    queued = client.post(f"/api/documents/{failed['id']}/reprocess")
    assert queued.status_code == 202 and queued.json()["status"] == "uploaded"
    # Processed again; same file, so the same outcome, and no chunks.
    (again,) = documents(client, kb_id)
    assert (again["status"], again["chunk_count"]) == ("failed", 0)


def test_a_document_already_in_progress_cannot_be_queued_twice(client, db, alice):
    act_as(client, alice)
    kb_id = new_kb(client)
    upload(client, kb_id, "a.txt", b"Some text.")
    (document,) = documents(client, kb_id)
    db.get(Document, uuid.UUID(document["id"])).status = "processing"
    db.commit()
    busy = client.post(f"/api/documents/{document['id']}/reprocess")
    assert busy.status_code == 409
    assert "already being processed (processing)" in busy.json()["error"]["message"]


# --- rejected at upload: nothing is stored -------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "data", "status", "code"),
    [
        ("program.exe", b"MZ\x90\x00", 415, "unsupported_file"),
        ("fake.pdf", b"MZ\x90\x00 not a pdf", 415, "unsupported_file"),
        ("old.docx", b"\xd0\xcf\x11\xe0 legacy word", 415, "unsupported_file"),
        ("bomb.docx", sample_files.zip_bomb_docx(), 422, "invalid_file"),
        ("empty.txt", b"", 422, "invalid_file"),
        ("big.txt", b"x" * (MAX_MB * 1024 * 1024 + 1), 413, "payload_too_large"),
    ],
)
def test_bad_uploads_are_refused_and_leave_nothing_behind(
    client, alice, uploads, filename, data, status, code
):
    act_as(client, alice)
    kb_id = new_kb(client)
    response = upload(client, kb_id, filename, data)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert documents(client, kb_id) == []
    assert stored_files(uploads) == []


def test_an_upload_without_a_file_field_is_refused(client, alice):
    act_as(client, alice)
    kb_id = new_kb(client)
    response = client.post(f"/api/knowledge-bases/{kb_id}/documents", data={"other": "x"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_file"


def test_the_same_file_twice_in_one_knowledge_base_is_a_conflict(client, alice, uploads):
    act_as(client, alice)
    kb_id, other_kb = new_kb(client), new_kb(client)
    data = sample_files.MARKDOWN.encode()
    assert upload(client, kb_id, "a.md", data).status_code == 202
    duplicate = upload(client, kb_id, "renamed-copy.md", data)  # same bytes, other name
    assert duplicate.status_code == 409
    assert len(stored_files(uploads)) == 1  # the duplicate's file was removed
    assert upload(client, other_kb, "a.md", data).status_code == 202  # fine elsewhere


# --- delete --------------------------------------------------------------------------------------


def test_deleting_a_document_removes_its_row_and_file(client, alice, uploads):
    act_as(client, alice)
    kb_id = new_kb(client)
    upload(client, kb_id, "a.txt", b"Some text.")
    (document,) = documents(client, kb_id)
    assert client.delete(f"/api/documents/{document['id']}").status_code == 204
    assert documents(client, kb_id) == []
    assert stored_files(uploads) == []
    assert client.delete(f"/api/documents/{document['id']}").status_code == 404


def test_deleting_a_knowledge_base_removes_its_upload_folder(client, alice, uploads):
    act_as(client, alice)
    kb_id = new_kb(client)
    upload(client, kb_id, "a.txt", b"Some text.")
    assert (uploads / kb_id).is_dir()
    assert client.delete(f"/api/knowledge-bases/{kb_id}").status_code == 204
    assert not (uploads / kb_id).exists()


# --- tenant isolation ----------------------------------------------------------------------------


def body_without_request_id(response):
    error = response.json()["error"]
    error.pop("request_id")
    return response.status_code, error


def test_bob_cannot_reach_alices_documents_or_chunks(client, alice, bob, uploads):
    act_as(client, alice)
    kb_id = new_kb(client)
    upload(client, kb_id, "policy.md", sample_files.MARKDOWN.encode())  # ready, with chunks
    (document,) = documents(client, kb_id)
    files_before = stored_files(uploads)

    act_as(client, bob)
    random_kb, random_doc = uuid.uuid4(), uuid.uuid4()
    pairs = [
        (upload(client, kb_id, "x.txt", b"bob was here"), upload(client, random_kb, "x.txt", b"y")),
        (
            client.get(f"/api/knowledge-bases/{kb_id}/documents"),
            client.get(f"/api/knowledge-bases/{random_kb}/documents"),
        ),
        (
            client.delete(f"/api/documents/{document['id']}"),
            client.delete(f"/api/documents/{random_doc}"),
        ),
        (
            client.get(f"/api/documents/{document['id']}"),
            client.get(f"/api/documents/{random_doc}"),
        ),
        (
            client.get(f"/api/documents/{document['id']}/chunks"),
            client.get(f"/api/documents/{random_doc}/chunks"),
        ),
        (
            client.post(f"/api/documents/{document['id']}/reprocess"),
            client.post(f"/api/documents/{random_doc}/reprocess"),
        ),
    ]
    for theirs, missing in pairs:
        assert theirs.status_code == 404
        assert body_without_request_id(theirs) == body_without_request_id(missing)
    assert stored_files(uploads) == files_before  # Bob's upload never reached the disk

    act_as(client, alice)
    (unchanged,) = documents(client, kb_id)
    assert (unchanged["id"], unchanged["status"]) == (document["id"], "ready")
    assert unchanged["chunk_count"] == document["chunk_count"] > 0


# --- background job edge cases -------------------------------------------------------------------


def test_a_restart_marks_interrupted_jobs_failed_but_not_new_uploads(client, db, alice):
    act_as(client, alice)
    kb_id = uuid.UUID(new_kb(client))
    started_at = datetime.now(UTC)

    def document(status, created_at):
        return Document(
            kb_id=kb_id,
            original_filename=f"{status}.txt",
            stored_path=f"{kb_id}/{uuid.uuid4()}.txt",
            file_type="txt",
            size_bytes=1,
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            status=status,
            created_at=created_at,
        )

    earlier = started_at - timedelta(minutes=5)
    waiting = save(db, document("uploaded", earlier))
    running = save(db, document("processing", earlier))
    finished = save(db, document("ready", earlier))
    just_uploaded = save(db, document("uploaded", started_at + timedelta(seconds=1)))

    @contextmanager
    def shared_session():
        yield db

    assert recover_interrupted(shared_session, started_at) == 2
    db.expire_all()
    statuses = {d.id: (d.status, d.error_message) for d in db.scalars(select(Document))}
    assert statuses[waiting.id] == statuses[running.id] == ("failed", INTERRUPTED)
    assert statuses[finished.id][0] == "ready"
    assert statuses[just_uploaded.id][0] == "uploaded"  # arrived after startup: left alone


def test_a_job_for_a_deleted_document_stops_quietly(db, uploads, caplog):
    @contextmanager
    def shared_session():
        yield db

    caplog.set_level("INFO")
    config = ChunkingConfig(embedding_model="BAAI/bge-small-en-v1.5")
    process_document(shared_session, Storage(uploads), config, uuid.uuid4())  # no such document
    assert "no longer waiting" in caplog.text
    assert "crashed" not in caplog.text


# --- chunks (M8) --------------------------------------------------------------------------------


def chunk_rows(db, document_id):
    db.expire_all()
    query = (
        select(Chunk).where(Chunk.document_id == uuid.UUID(document_id)).order_by(Chunk.chunk_index)
    )
    return list(db.scalars(query))


def test_a_processed_markdown_document_has_heading_aware_chunks(client, db, alice):
    act_as(client, alice)
    kb_id = new_kb(client)
    upload(client, kb_id, "policy.md", sample_files.MARKDOWN.encode())
    (document,) = documents(client, kb_id)
    rows = chunk_rows(db, document["id"])
    assert document["status"] == "ready"
    assert document["chunk_count"] == len(rows) > 0
    assert [r.chunk_index for r in rows] == list(range(len(rows)))
    assert {str(r.kb_id) for r in rows} == {kb_id}  # copied for KB-filtered search
    assert {r.strategy for r in rows} == {"heading"}
    assert all(r.text.startswith("NX-HR-002 v3.0") for r in rows)  # the context header

    page = client.get(f"/api/documents/{document['id']}/chunks").json()
    assert page["total"] == len(rows)
    assert [c["chunk_index"] for c in page["items"]] == list(range(len(rows)))
    leave = next(c for c in page["items"] if "24 days" in c["text"])
    assert leave["section"] == "4. Leave Types › 4.2 Annual leave – 4.3 Sick leave"
    assert leave["token_count"] <= 510


def test_pdf_chunks_carry_page_numbers(client, db, alice):
    act_as(client, alice)
    kb_id = new_kb(client)
    pages = [f"Page {n}: " + " ".join(["leave policy text"] * 60) for n in (1, 2, 3)]
    upload(client, kb_id, "p.pdf", sample_files.pdf(*pages))
    (document,) = documents(client, kb_id)
    rows = chunk_rows(db, document["id"])
    assert {r.strategy for r in rows} == {"recursive"}  # a PDF has no headings
    assert rows[0].page_start == 1 and rows[-1].page_end == 3
    assert all(r.page_start <= r.page_end for r in rows)


def test_the_chunk_inspector_pages_through_chunks(client, alice):
    act_as(client, alice)
    kb_id = new_kb(client)
    upload(client, kb_id, "policy.md", sample_files.MARKDOWN.encode())
    (document,) = documents(client, kb_id)
    url = f"/api/documents/{document['id']}/chunks"
    first = client.get(url, params={"limit": 1}).json()
    second = client.get(url, params={"limit": 1, "offset": 1}).json()
    assert first["total"] == second["total"] == document["chunk_count"]
    assert first["items"][0]["chunk_index"] == 0 and second["items"][0]["chunk_index"] == 1
    assert client.get(url, params={"limit": 500}).status_code == 422  # capped at 200


def test_reprocessing_replaces_chunks_instead_of_adding_to_them(client, db, alice):
    act_as(client, alice)
    kb_id = new_kb(client)
    upload(client, kb_id, "policy.md", sample_files.MARKDOWN.encode())
    (document,) = documents(client, kb_id)
    before = {r.id for r in chunk_rows(db, document["id"])}

    assert client.post(f"/api/documents/{document['id']}/reprocess").status_code == 202
    after = chunk_rows(db, document["id"])
    assert len(after) == len(before)  # same text, same chunks...
    assert before.isdisjoint({r.id for r in after})  # ...but a fresh set, not duplicates


def test_a_reprocess_that_now_fails_removes_the_old_chunks(client, db, alice, uploads):
    act_as(client, alice)
    kb_id = new_kb(client)
    upload(client, kb_id, "a.txt", b"Some useful text about leave.")
    (document,) = documents(client, kb_id)
    assert len(chunk_rows(db, document["id"])) == 1
    (uploads / kb_id / f"{document['id']}.txt").write_bytes(b"   ")  # now there's no text

    client.post(f"/api/documents/{document['id']}/reprocess")
    (again,) = documents(client, kb_id)
    assert (again["status"], again["chunk_count"]) == ("failed", 0)
    assert chunk_rows(db, document["id"]) == []  # never "failed" with stale chunks


def test_deleting_a_document_deletes_its_chunks(client, db, alice):
    act_as(client, alice)
    kb_id = new_kb(client)
    upload(client, kb_id, "policy.md", sample_files.MARKDOWN.encode())
    (document,) = documents(client, kb_id)
    assert chunk_rows(db, document["id"])
    client.delete(f"/api/documents/{document['id']}")
    assert chunk_rows(db, document["id"]) == []
