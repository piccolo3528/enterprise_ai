"""Documents: upload into a knowledge base, list, delete, retry.

Endpoints: upload, list (per knowledge base), get, chunks (inspector), reprocess, delete.

The upload route reads the multipart body itself instead of declaring an `UploadFile`
parameter. FastAPI parses declared form/file parameters *before* running dependencies, so a
signed-out caller (or one uploading to someone else's knowledge base) could make the server
receive and spool an entire upload first. Here the order is:
    session cookie (401) -> knowledge base ownership (404) -> Content-Length (411/413)
    -> read the body -> checks + save -> 202, then processing continues in the background.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, Request, status
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.api.deps import (
    CurrentUserId,
    DbSession,
    DocumentId,
    KbId,
    ReadDbSession,
    SessionFactoryDep,
    SettingsDep,
    StorageDep,
    VectorStoreDep,
)
from app.core.errors import InvalidFileError, LengthRequiredError, PayloadTooLargeError
from app.schemas.document import ChunkPage, DocumentList, DocumentOut
from app.services import documents as service
from app.services.ingestion.pipeline import IngestionConfig, process_document

router = APIRouter(tags=["documents"])

# Multipart wraps the file in boundaries and part headers; allow for them on top of the file.
_FORM_OVERHEAD = 64 * 1024


@router.post(
    "/knowledge-bases/{kb_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    request: Request,
    user_id: CurrentUserId,
    kb_id: KbId,
    db: DbSession,
    settings: SettingsDep,
    storage: StorageDep,
    vectors: VectorStoreDep,
    session_factory: SessionFactoryDep,
    background: BackgroundTasks,
):
    """Upload one file (form field `file`): PDF, DOCX, TXT or MD, up to MAX_UPLOAD_MB.

    202 Accepted: the file is stored and queued; poll the document list for `ready`/`failed`.
    """
    await run_in_threadpool(service.require_owned_kb, db, user_id, kb_id)

    max_bytes = settings.max_upload_mb * 1024 * 1024
    declared = request.headers.get("content-length")
    if declared is None or not declared.isdigit():
        raise LengthRequiredError("The upload must declare its size (Content-Length).")
    if int(declared) > max_bytes + _FORM_OVERHEAD:
        raise PayloadTooLargeError(f"The file is larger than {settings.max_upload_mb} MB.")

    form = await request.form(max_files=1, max_fields=1)
    try:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise InvalidFileError("Choose a file to upload (form field 'file').")
        document = await run_in_threadpool(
            service.add_document,
            db,
            storage,
            user_id,
            kb_id,
            filename=upload.filename,
            source=upload.file,
            max_bytes=max_bytes,
        )
    finally:
        await form.close()  # deletes the multipart parser's temporary copy

    # Runs after the response is sent, in a worker thread (process_document is a plain def).
    config = IngestionConfig.from_settings(settings)
    background.add_task(process_document, session_factory, storage, vectors, config, document.id)
    return document


@router.get("/knowledge-bases/{kb_id}/documents", response_model=DocumentList)
def list_documents(user_id: CurrentUserId, kb_id: KbId, db: ReadDbSession):
    """The knowledge base's documents, newest first. The UI polls this while any is processing."""
    return DocumentList(items=service.list_documents(db, user_id, kb_id))


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    user_id: CurrentUserId,
    document_id: DocumentId,
    db: DbSession,
    storage: StorageDep,
    vectors: VectorStoreDep,
) -> None:
    """Removes the document's vectors, its rows and its file. 503 if the vector database is
    unreachable: the document is then left `deleting`, and deleting it again finishes the job."""
    service.delete_document(db, storage, vectors, user_id, document_id)


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(user_id: CurrentUserId, document_id: DocumentId, db: ReadDbSession):
    return service.get_document(db, user_id, document_id)


@router.get("/documents/{document_id}/chunks", response_model=ChunkPage)
def list_chunks(
    user_id: CurrentUserId,
    document_id: DocumentId,
    db: ReadDbSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """The chunk inspector: the document's chunks in order, a page at a time."""
    chunks, total = service.list_chunks(db, user_id, document_id, offset=offset, limit=limit)
    return ChunkPage(items=chunks, total=total, offset=offset, limit=limit)


@router.post(
    "/documents/{document_id}/reprocess",
    response_model=DocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def reprocess_document(
    user_id: CurrentUserId,
    document_id: DocumentId,
    db: DbSession,
    settings: SettingsDep,
    storage: StorageDep,
    vectors: VectorStoreDep,
    session_factory: SessionFactoryDep,
    background: BackgroundTasks,
):
    """Process a failed or ready document again (e.g. after a restart, or after changing the
    chunking settings). 409 while it is already queued or processing."""
    document = service.reprocess_document(db, user_id, document_id)
    config = IngestionConfig.from_settings(settings)
    background.add_task(process_document, session_factory, storage, vectors, config, document.id)
    return document
