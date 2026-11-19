"""Grounded answers with citations from one knowledge base (M12; non-streamed, not saved).

Conversations, history and streaming come in M13 (POST /api/conversations/{id}/messages).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserId, KbId, LLMDep, ReadDbSession, SettingsDep, VectorStoreDep
from app.schemas.answers import AskRequest, AskResponse, CitationOut
from app.services import rag
from app.services.embeddings import get_embedder

router = APIRouter(tags=["answers"])


def _citation(c: rag.Citation) -> CitationOut:
    p = c.result.passage
    meta = p.doc_metadata or {}

    def text_or_none(key: str) -> str | None:
        value = meta.get(key)
        return str(value) if value is not None else None

    return CitationOut(
        number=c.number,
        chunk_id=p.chunk_id,
        document_id=p.document_id,
        filename=p.filename,
        doc_code=text_or_none("document_id"),
        doc_version=text_or_none("version"),
        doc_status=text_or_none("status"),
        doc_title=text_or_none("title"),
        section=p.section,
        page_start=p.page_start,
        page_end=p.page_end,
        text=p.text,
        flagged=c.flagged,
    )


@router.post("/knowledge-bases/{kb_id}/ask", response_model=AskResponse)
def ask_knowledge_base(
    body: AskRequest,
    user_id: CurrentUserId,
    kb_id: KbId,
    db: ReadDbSession,
    settings: SettingsDep,
    vectors: VectorStoreDep,
    llm: LLMDep,
):
    """Answer from the knowledge base's ready documents, citing them. 404 for a knowledge base
    that isn't yours; 429 `rate_limited` / `quota_exhausted`; 503 `llm_unavailable` /
    `llm_not_configured`; 422 `answer_blocked`."""
    result = rag.answer_question(
        db,
        vectors,
        lambda: get_embedder(settings.embedding_model),
        llm,
        owner_id=user_id,
        kb_id=kb_id,
        question=body.question,
        candidates=settings.retrieval_top_k,
        max_sources=settings.context_max_sources,
        token_budget=settings.context_token_budget,
    )
    return AskResponse(
        answer=result.answer,
        not_found=result.not_found,
        citations=[_citation(c) for c in result.citations],
        notices=result.notices,
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        output_tokens=result.output_tokens,
        sources_given=result.sources_given,
        invalid_citations=result.invalid_citations,
        prompt_version=result.prompt_version,
        timings_ms=result.timings_ms,
    )
