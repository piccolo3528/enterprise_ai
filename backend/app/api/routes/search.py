"""Search inside one knowledge base: returns passages, never an LLM answer (that is M12)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserId, KbId, ReadDbSession, SettingsDep, VectorStoreDep
from app.schemas.search import SearchRequest, SearchResponse, SearchResultOut
from app.services import retrieval
from app.services.embeddings import get_embedder
from app.services.retrieval import SearchResult

router = APIRouter(tags=["search"])


def _to_out(result: SearchResult) -> SearchResultOut:
    p = result.passage
    meta = p.doc_metadata or {}
    return SearchResultOut(
        chunk_id=p.chunk_id,
        document_id=p.document_id,
        filename=p.filename,
        doc_code=meta.get("document_id"),
        doc_version=meta.get("version"),
        doc_status=meta.get("status"),
        chunk_index=p.chunk_index,
        section=p.section,
        page_start=p.page_start,
        page_end=p.page_end,
        text=p.text,
        score=result.score,
        semantic_rank=result.semantic_rank,
        semantic_score=result.semantic_score,
        keyword_rank=result.keyword_rank,
        keyword_score=result.keyword_score,
        keyword_matched=result.keyword_matched,
    )


@router.post("/knowledge-bases/{kb_id}/search", response_model=SearchResponse)
def search_knowledge_base(
    body: SearchRequest,
    user_id: CurrentUserId,
    kb_id: KbId,
    db: ReadDbSession,
    settings: SettingsDep,
    vectors: VectorStoreDep,
):
    """Semantic, keyword or hybrid search. 404 for a knowledge base (or document) that isn't
    yours; 503 if semantic search is asked for while the vector database is unreachable."""
    outcome = retrieval.search(
        db,
        vectors,
        lambda: get_embedder(settings.embedding_model),
        owner_id=user_id,
        kb_id=kb_id,
        query=body.query,
        mode=body.mode,
        top_k=body.top_k,
        candidates=settings.retrieval_top_k,
        min_score=body.min_score,
        document_id=body.document_id,
    )
    return SearchResponse(
        mode=outcome.mode,
        results=[_to_out(r) for r in outcome.results],
        query_terms=outcome.query_terms,
        notice=outcome.notice,
        timings_ms=outcome.timings_ms,
    )
