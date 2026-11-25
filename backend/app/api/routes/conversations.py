"""Conversations: streamed answers with memory, and the list/read/rename/delete around them (M13).

    POST   /api/knowledge-bases/{kb_id}/conversations   first question -> SSE (creates it)
    POST   /api/conversations/{id}/messages             follow-up question -> SSE
    GET    /api/knowledge-bases/{kb_id}/conversations   the sidebar list, most recent first
    GET    /api/conversations/{id}                      one conversation with its messages
    PATCH  /api/conversations/{id}                      rename
    DELETE /api/conversations/{id}                      delete (messages go with it)

**Streaming (§3.3, D68).** The two POSTs answer `text/event-stream`. Everything that can be
checked before the answer starts (session, input, ownership, LLM configured) is a normal JSON
error with its HTTP status; once the stream has started (200), failures arrive as an `error`
event. Each event is `event: <name>` + `data: <JSON>`. A POST can't use the browser's
EventSource (GET only), so the frontend reads the stream with fetch().

The answer pipeline is synchronous (SQLAlchemy, the Gemini SDK), so each step runs in a worker
thread; this async wrapper only forwards events. When the browser disconnects (Stop), Starlette
cancels the response, and the generator is closed, which saves what was shown (rag.py).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterator

import anyio
from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
    ConversationId,
    CurrentUserId,
    DbSession,
    KbId,
    LimitsDep,
    LLMDep,
    ReadDbSession,
    ReadSessionFactoryDep,
    SessionFactoryDep,
    SettingsDep,
    VectorStoreDep,
)
from app.schemas.answers import AskRequest
from app.schemas.conversations import (
    ConversationDetail,
    ConversationList,
    ConversationOut,
    ConversationRename,
    MessageOut,
)
from app.services import conversations, rag, retrieval
from app.services.embeddings import get_embedder
from app.services.history import select_history
from app.services.ingestion.tokens import get_tokens

router = APIRouter(tags=["conversations"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # tells a reverse proxy (nginx) not to buffer the stream
}
_STREAM_DOC = {200: {"description": "Server-Sent Events", "content": {"text/event-stream": {}}}}


def sse(name: str, data: object) -> str:
    """One Server-Sent Event. JSON data never contains a raw line break, so one `data:` line."""
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"


async def event_stream(events: Iterator[rag.Event]) -> AsyncIterator[str]:
    """Forward the pipeline's events, running each step in a worker thread. On disconnect the
    pending step finishes, then the generator is closed (shielded from the cancellation, so the
    "stopped" answer is saved and the Gemini stream closed)."""
    try:
        while (event := await anyio.to_thread.run_sync(next, events, None)) is not None:
            yield sse(*event)
    finally:
        with anyio.CancelScope(shield=True):
            await anyio.to_thread.run_sync(events.close)


def _respond(events: Iterator[rag.Event]) -> StreamingResponse:
    return StreamingResponse(
        event_stream(events), media_type="text/event-stream", headers=SSE_HEADERS
    )


@router.post("/knowledge-bases/{kb_id}/conversations", responses=_STREAM_DOC)
def start_conversation(
    body: AskRequest,
    user_id: CurrentUserId,
    kb_id: KbId,
    db: ReadDbSession,
    settings: SettingsDep,
    vectors: VectorStoreDep,
    llm: LLMDep,
    sessions: SessionFactoryDep,
    read_sessions: ReadSessionFactoryDep,
    limits: LimitsDep,
):
    """Ask the first question of a new conversation; the answer streams back. The conversation
    is saved with its first answer (its id comes in the first event); nothing is saved if the
    answer fails."""
    limits.question(str(user_id))  # 429 before any database or LLM work (M16)
    # 404 unless the KB is yours (and the document, if one was chosen, is in it). One query.
    retrieval.check_scope(db, user_id, kb_id, body.document_id)
    db.close()  # release the connection now: the stream outlives this function
    turn = rag.Turn(user_id, kb_id, uuid.uuid4(), new=True, history=[])
    return _respond(
        rag.stream_answer(
            read_sessions,
            sessions,
            vectors,
            lambda: get_embedder(settings.embedding_model),
            llm,
            turn=turn,
            question=body.question,
            settings=rag.answer_settings(settings, body.multi_query),
            document_id=body.document_id,
        )
    )


@router.post("/conversations/{conversation_id}/messages", responses=_STREAM_DOC)
def ask_follow_up(
    body: AskRequest,
    user_id: CurrentUserId,
    conversation_id: ConversationId,
    db: ReadDbSession,
    settings: SettingsDep,
    vectors: VectorStoreDep,
    llm: LLMDep,
    sessions: SessionFactoryDep,
    read_sessions: ReadSessionFactoryDep,
    limits: LimitsDep,
):
    """Ask a follow-up. It is rewritten as a standalone question using the recent turns
    (HISTORY_MAX_TURNS, HISTORY_TOKEN_BUDGET), then answered like a first question."""
    limits.question(str(user_id))
    kb_id, messages = conversations.load_for_follow_up(
        db, user_id, conversation_id, max_turns=settings.history_max_turns
    )
    if body.document_id:
        retrieval.check_scope(db, user_id, kb_id, body.document_id)
    db.close()
    history = select_history(
        messages, budget=settings.history_token_budget, tokens=get_tokens(settings.embedding_model)
    )
    turn = rag.Turn(user_id, kb_id, conversation_id, new=False, history=history)
    return _respond(
        rag.stream_answer(
            read_sessions,
            sessions,
            vectors,
            lambda: get_embedder(settings.embedding_model),
            llm,
            turn=turn,
            question=body.question,
            settings=rag.answer_settings(settings, body.multi_query),
            document_id=body.document_id,
        )
    )


@router.get("/knowledge-bases/{kb_id}/conversations", response_model=ConversationList)
def list_conversations(user_id: CurrentUserId, kb_id: KbId, db: ReadDbSession):
    """Your conversations about this knowledge base, most recently active first (at most 100)."""
    items = conversations.list_conversations(db, user_id, kb_id)
    return ConversationList(items=[ConversationOut.model_validate(c) for c in items])


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(user_id: CurrentUserId, conversation_id: ConversationId, db: ReadDbSession):
    """The conversation with every message in order, answers with their saved citations."""
    conversation, messages = conversations.get_conversation(db, user_id, conversation_id)
    return ConversationDetail(
        **ConversationOut.model_validate(conversation).model_dump(),
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def rename_conversation(
    user_id: CurrentUserId, conversation_id: ConversationId, body: ConversationRename, db: DbSession
):
    return ConversationOut.model_validate(
        conversations.rename_conversation(db, user_id, conversation_id, body.title)
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(user_id: CurrentUserId, conversation_id: ConversationId, db: DbSession):
    conversations.delete_conversation(db, user_id, conversation_id)
