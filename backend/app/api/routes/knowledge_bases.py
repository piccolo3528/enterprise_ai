"""/api/knowledge-bases: the signed-in user's knowledge bases.

Thin routes: they read the caller's id from the session cookie (no database query), pass it to
the service, and the service puts it into every SQL statement. Reads use the autocommit session
(D27); writes use a transaction. `user_id` comes first in every signature: FastAPI resolves
dependencies in order, so a signed-out caller always gets 401 before the id is even looked at.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import (
    CurrentUserId,
    DbSession,
    KbId,
    ReadDbSession,
    StorageDep,
    VectorStoreDep,
)
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseList,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
)
from app.services import knowledge_bases as service

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge bases"])


def _out(summary: service.KnowledgeBaseSummary) -> KnowledgeBaseOut:
    return KnowledgeBaseOut.model_validate(summary.as_dict())


@router.get("", response_model=KnowledgeBaseList)
def list_knowledge_bases(user_id: CurrentUserId, db: ReadDbSession):
    """Your knowledge bases with document and conversation counts, most recently changed first."""
    return KnowledgeBaseList(items=[_out(s) for s in service.list_knowledge_bases(db, user_id)])


@router.post("", response_model=KnowledgeBaseOut, status_code=status.HTTP_201_CREATED)
def create_knowledge_base(body: KnowledgeBaseCreate, user_id: CurrentUserId, db: DbSession):
    """Names are unique per user, ignoring case (409 if taken)."""
    return _out(
        service.create_knowledge_base(db, user_id, name=body.name, description=body.description)
    )


@router.get("/{kb_id}", response_model=KnowledgeBaseOut)
def get_knowledge_base(user_id: CurrentUserId, kb_id: KbId, db: ReadDbSession):
    """404 if it doesn't exist *or* isn't yours: the answer never reveals which."""
    return _out(service.get_knowledge_base(db, user_id, kb_id))


@router.patch("/{kb_id}", response_model=KnowledgeBaseOut)
def update_knowledge_base(
    user_id: CurrentUserId, kb_id: KbId, body: KnowledgeBaseUpdate, db: DbSession
):
    """Rename and/or change the description; fields you don't send are left alone."""
    return _out(service.update_knowledge_base(db, user_id, kb_id, body.changes()))


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_base(
    user_id: CurrentUserId,
    kb_id: KbId,
    db: DbSession,
    storage: StorageDep,
    vectors: VectorStoreDep,
) -> None:
    """Deletes the knowledge base and everything in it: vectors, rows and uploaded files. Can't
    be undone. 503 if the vector database is unreachable (then nothing is deleted yet)."""
    service.delete_knowledge_base(db, vectors, user_id, kb_id)
    # After the commit: if removing the folder fails, the rows are gone and the files are
    # harmless leftovers (logged), never rows pointing at missing files.
    storage.delete_knowledge_base(kb_id)
