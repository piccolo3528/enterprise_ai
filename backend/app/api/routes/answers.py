"""Grounded answers with citations from one knowledge base (M12; non-streamed, not saved).

The chat uses the streamed, saved version (routes/conversations.py, M13). This one stays for
scripts and evaluations: one question, one JSON response.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import (
    CurrentUserId,
    KbId,
    LimitsDep,
    LLMDep,
    ReadDbSession,
    SettingsDep,
    VectorStoreDep,
)
from app.schemas.answers import AskRequest, AskResponse, CitationOut
from app.services import rag, retrieval
from app.services.embeddings import get_embedder

router = APIRouter(tags=["answers"])


def _citation(c: rag.Citation) -> CitationOut:
    return CitationOut.model_validate(c.snapshot())


@router.post("/knowledge-bases/{kb_id}/ask", response_model=AskResponse)
def ask_knowledge_base(
    body: AskRequest,
    user_id: CurrentUserId,
    kb_id: KbId,
    db: ReadDbSession,
    settings: SettingsDep,
    vectors: VectorStoreDep,
    llm: LLMDep,
    limits: LimitsDep,
):
    """Answer from the knowledge base's ready documents, citing them. 404 for a knowledge base
    that isn't yours; 429 `rate_limited` (also your per-user question limit, M16) /
    `quota_exhausted`; 503 `llm_unavailable` / `llm_not_configured`; 422 `answer_blocked`."""
    limits.question(str(user_id))
    # Ownership first (M16, found by the authz matrix): the planning call below would otherwise
    # spend a Gemini request before retrieval's own check answered 404 for someone else's KB.
    retrieval.check_scope(db, user_id, kb_id, body.document_id)
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
        settings=rag.answer_settings(settings, body.multi_query),
        document_id=body.document_id,
    )
    return AskResponse(
        answer=result.answer,
        not_found=result.not_found,
        citations=[_citation(c) for c in result.citations],
        related=[_citation(c) for c in result.related],
        notices=result.notices,
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        output_tokens=result.output_tokens,
        sources_given=result.sources_given,
        invalid_citations=result.invalid_citations,
        prompt_version=result.prompt_version,
        timings_ms=result.timings_ms,
    )
