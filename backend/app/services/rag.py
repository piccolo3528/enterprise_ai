"""Answering a question from one knowledge base: retrieve -> build context -> generate ->
validate citations (ARCHITECTURE §3.2; non-streamed in M12, streamed in M13).

    question ──► hybrid retrieval (top CONTEXT_MAX_SOURCES, ready documents of the caller's KB)
                 │  nothing found? ──► "not found", no LLM call
                 ▼
             release the database connection (the LLM takes seconds; Neon's pool is small)
                 ▼
             context: numbered, labelled, escaped sources within the token budget; flag
             passages that look like injection attempts
                 ▼
             Gemini (system rules + sources + question)
                 │  replied NOT_FOUND? ──► "not found" (D62: no retrieval score could decide it)
                 ▼
             citations: drop numbers that weren't given, renumber 1..m in order of use

At most one LLM call per question. Logs carry sizes, counts, ids and timings, never the question,
the passages or the answer.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.services import retrieval
from app.services.citations import resolve_citations
from app.services.context_builder import Source, build_context
from app.services.embeddings import Embedder
from app.services.llm.base import LLMProvider
from app.services.llm.prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt, is_not_found
from app.services.retrieval import SearchResult
from app.services.vector_store import VectorStore

logger = logging.getLogger("app.rag")

NOT_FOUND_ANSWER = "I couldn't find the answer to that in this knowledge base's documents."
NO_CITATIONS = (
    "This answer doesn't cite any of your documents, so it may not come from them. Check it "
    "before relying on it."
)
TRUNCATED = "The answer reached the length limit and may be cut off."
FLAGGED = (
    "A cited passage contains text that looks like instructions to an AI. It was treated as "
    "document content, but read that source critically."
)


@dataclass(frozen=True)
class Citation:
    number: int  # as shown in the answer: [1], [2], ...
    result: SearchResult
    flagged: bool


@dataclass
class RagAnswer:
    answer: str
    not_found: bool
    citations: list[Citation] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    model: str | None = None  # None when no LLM call was made
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    sources_given: int = 0  # passages in the prompt
    invalid_citations: int = 0
    prompt_version: str = PROMPT_VERSION
    timings_ms: dict[str, float] = field(default_factory=dict)


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def answer_question(
    db: Session,
    vectors: VectorStore,
    embedder: Callable[[], Embedder],
    llm: LLMProvider,
    *,
    owner_id: uuid.UUID,
    kb_id: uuid.UUID,
    question: str,
    candidates: int,
    max_sources: int,
    token_budget: int,
) -> RagAnswer:
    started = time.perf_counter()
    timings: dict[str, float] = {}

    outcome = retrieval.search(
        db, vectors, embedder,
        owner_id=owner_id, kb_id=kb_id, query=question,
        mode="hybrid", top_k=max_sources, candidates=candidates,
    )  # fmt: skip
    timings["retrieval"] = outcome.timings_ms.get("total", 0.0)
    # The session keeps its pooled connection until closed, even in autocommit mode (measured:
    # 1 checked out after a SELECT, 0 after close()). Release it before waiting seconds for the
    # LLM; the session would reconnect if used again.
    db.close()
    notices = [outcome.notice] if outcome.notice else []  # e.g. "semantic search unavailable"

    if not outcome.results:
        timings["total"] = _ms(started)
        _log(question, 0, 0, True, 0, 0, None, timings)
        return RagAnswer(NOT_FOUND_ANSWER, True, notices=notices, timings_ms=timings)

    t = time.perf_counter()
    context = build_context(outcome.results, max_sources=max_sources, token_budget=token_budget)
    prompt = build_user_prompt(question, [s.prompt_input() for s in context.sources])
    timings["build_prompt"] = _ms(t)
    flagged = [s for s in context.sources if s.flagged]
    if flagged:
        logger.warning(
            "Possible prompt injection in chunk(s) %s",
            ", ".join(str(s.result.passage.chunk_id) for s in flagged),
        )

    result = llm.generate(system=SYSTEM_PROMPT, prompt=prompt)
    timings.update(result.timings_ms)
    answer = RagAnswer(
        answer="",
        not_found=False,
        notices=notices,
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        output_tokens=result.output_tokens,
        sources_given=len(context.sources),
        timings_ms=timings,
    )

    if is_not_found(result.text):
        answer.answer, answer.not_found = NOT_FOUND_ANSWER, True
    else:
        resolved = resolve_citations(result.text, len(context.sources))
        by_number: dict[int, Source] = {s.number: s for s in context.sources}
        answer.answer = resolved.text
        answer.invalid_citations = resolved.invalid
        answer.citations = [
            Citation(new, by_number[old].result, by_number[old].flagged)
            for new, old in enumerate(resolved.order, start=1)
        ]
        if not answer.citations:
            notices.append(NO_CITATIONS)
        if any(c.flagged for c in answer.citations):
            notices.append(FLAGGED)
        if result.finish_reason == "max_tokens":
            notices.append(TRUNCATED)

    timings["total"] = _ms(started)
    _log(question, len(context.sources), len(flagged), answer.not_found,
         len(answer.citations), answer.invalid_citations, result, timings)  # fmt: skip
    return answer


def _log(question, sources, flagged, not_found, cited, invalid, result, timings) -> None:
    logger.info(
        "Answer question_chars=%d sources=%d flagged=%d not_found=%s cited=%d invalid=%d "
        "model=%s attempts=%s prompt_tokens=%s output_tokens=%s timings_ms=%s",
        len(question), sources, flagged, not_found, cited, invalid,
        result.model if result else None, result.attempts if result else 0,
        result.prompt_tokens if result else None, result.output_tokens if result else None,
        timings,
    )  # fmt: skip
