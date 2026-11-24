"""Answering a question from one knowledge base (ARCHITECTURE §3.2).

    follow-up? ──► rewrite it as a standalone question (one utility-model call, JSON; M13)
                 ▼
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

Two entry points share these steps:
- `answer_question` (M12, POST /knowledge-bases/{id}/ask): one question, one JSON response, not
  saved. Kept for scripts and evaluations.
- `stream_answer` (M13, the chat): events as the answer is written (status, token, citations,
  done or error, §3.3), with conversation memory, and the turn saved at the end.

At most two LLM calls per question (rewrite + answer). Logs carry sizes, counts, ids and timings,
never the question, the passages or the answer.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, LLMNotConfiguredError, QuotaExhaustedError
from app.services import answer_retrieval, conversations
from app.services.answer_retrieval import RetrievalSettings, Retrieved
from app.services.answer_stream import CitationStream, NotFoundGate
from app.services.citations import resolve_citations
from app.services.context_builder import Context, Order, Source, build_context, query_terms
from app.services.embeddings import Embedder
from app.services.llm.base import LLMProvider, LLMResult
from app.services.llm.prompts import (
    MULTI_QUERY_SCHEMA,
    MULTI_QUERY_SYSTEM_PROMPT,
    PROMPT_VERSION,
    REWRITE_MAX_OUTPUT_TOKENS,
    REWRITE_SCHEMA,
    REWRITE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_rewrite_prompt,
    build_user_prompt,
    is_not_found,
    parse_rewrite,
    parse_search_queries,
)
from app.services.reranker import Reranker, get_reranker
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
REWRITE_FAILED = (
    "This follow-up was searched as written: the earlier conversation couldn't be used to "
    "interpret it. If the answer misses the point, ask the full question."
)
UNEXPECTED = "Something went wrong on our side. Please try again."


def fallback_notice(model: str) -> str:
    """Shown on an answer written by a backup model of the fallback chain (D80)."""
    return (
        f"Answered by a backup model ({model}) because the main model is unavailable or has used "
        "up its daily free quota. Its answers were checked less thoroughly."
    )
REWRITE_MAX_CHARS = 1000  # the question length limit

SessionFactory = Callable[[], AbstractContextManager[Session]]
Event = tuple[str, Any]  # (event name, JSON-serialisable data)


@dataclass(frozen=True)
class Citation:
    number: int  # as shown in the answer: [1], [2], ...
    result: SearchResult
    flagged: bool

    def snapshot(self) -> dict[str, Any]:
        """What the reader is shown about the cited passage: sent in the `citations` event and
        saved with the answer, so a saved conversation still shows it after the document changes."""
        p = self.result.passage
        meta = p.doc_metadata or {}

        def text_or_none(key: str) -> str | None:
            value = meta.get(key)
            return str(value) if value is not None else None

        return {
            "number": self.number,
            "chunk_id": str(p.chunk_id),
            "document_id": str(p.document_id),
            "filename": p.filename,
            "doc_code": text_or_none("document_id"),
            "doc_version": text_or_none("version"),
            "doc_status": text_or_none("status"),
            "doc_title": text_or_none("title"),
            "section": p.section,
            "page_start": p.page_start,
            "page_end": p.page_end,
            "text": p.text,
            "flagged": self.flagged,
        }


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
    # Every passage in the prompt, in prompt order (the evaluation's judge needs exactly these)
    sources: list[Source] = field(default_factory=list)
    extra_queries: list[str] = field(default_factory=list)  # multi-query phrasings searched


@dataclass(frozen=True)
class AnswerSettings:
    candidates: int  # retrieval candidates per side (RETRIEVAL_TOP_K)
    max_sources: int  # CONTEXT_MAX_SOURCES
    token_budget: int  # CONTEXT_TOKEN_BUDGET
    rewrite_model: str | None = None  # GEMINI_MODEL_UTILITY; None = the answer model
    # M14: the retrieval stages (rerank, versions, amendments); None = plain hybrid search
    retrieval: RetrievalSettings | None = None
    reranker: Callable[[], Reranker] | None = None  # the cross-encoder, loaded once
    multi_query: bool = False  # extra phrasings from the planning call (MULTI_QUERY_ENABLED)
    # Context experiments (M15, D76): passage order, and extractive compression (needs `tokens`,
    # a TokenCounter, to re-count compressed passages against the budget)
    context_order: Order = "rank"
    compress: bool = False
    tokens: object | None = None

    def retrieval_settings(self) -> RetrievalSettings:
        return self.retrieval or RetrievalSettings(
            candidates=self.candidates, pool=self.max_sources, max_sources=self.max_sources
        )


def answer_settings(settings: Settings) -> AnswerSettings:
    """The answer pipeline as configured in backend/.env (shared by /ask and the chat)."""
    rerank = settings.rerank_enabled
    return AnswerSettings(
        candidates=settings.retrieval_top_k,
        max_sources=settings.context_max_sources,
        token_budget=settings.context_token_budget,
        rewrite_model=settings.gemini_model_utility,
        retrieval=RetrievalSettings(
            candidates=settings.retrieval_top_k,
            pool=settings.rerank_pool if rerank else settings.context_max_sources,
            max_sources=settings.context_max_sources,
            rerank=rerank,
            rerank_min_score=settings.rerank_min_score,
            version_mode=settings.version_mode,
            amendments=settings.amendments_enabled,
        ),
        reranker=(lambda: get_reranker(settings.reranker_model)) if rerank else None,
        multi_query=settings.multi_query_enabled,
    )


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


# --- steps shared by both entry points -----------------------------------------------------------


def _retrieve(db: Session, vectors, embedder, *, owner_id, kb_id, query: str,
              settings: AnswerSettings, extra_queries=(),
              document_id=None) -> Retrieved:  # fmt: skip
    return answer_retrieval.retrieve(
        db, vectors, embedder, settings.reranker,
        owner_id=owner_id, kb_id=kb_id, query=query, settings=settings.retrieval_settings(),
        extra_queries=extra_queries, document_id=document_id,
    )  # fmt: skip


def _retrieval_timings(retrieved: Retrieved) -> dict[str, float]:
    """The retrieval stages worth keeping with the answer: the total and the optional stages."""
    t = retrieved.timings_ms
    out = {"retrieval": t.get("retrieval_total", 0.0)}
    out.update({k: t[k] for k in ("rerank", "amendments") if k in t})
    return out


def _prepare(results: list[SearchResult], question: str, settings: AnswerSettings,
             extra_queries=()) -> tuple[Context, str]:  # fmt: skip
    context = build_context(
        results, max_sources=settings.max_sources, token_budget=settings.token_budget,
        order=settings.context_order,
        compress_terms=query_terms([question, *extra_queries]) if settings.compress else None,
        tokens=settings.tokens,
    )  # fmt: skip
    prompt = build_user_prompt(question, [s.prompt_input() for s in context.sources])
    flagged = [s for s in context.sources if s.flagged]
    if flagged:
        logger.warning(
            "Possible prompt injection in chunk(s) %s",
            ", ".join(str(s.result.passage.chunk_id) for s in flagged),
        )
    return context, prompt


def _cited(context: Context, order: list[int]) -> list[Citation]:
    """Citations numbered 1..m, from the original source numbers in order of first use."""
    by_number: dict[int, Source] = {s.number: s for s in context.sources}
    return [
        Citation(new, by_number[old].result, by_number[old].flagged)
        for new, old in enumerate(order, start=1)
    ]


def _answer_notices(citations: list[Citation], finish_reason: str | None) -> list[str]:
    notices = []
    if not citations:
        notices.append(NO_CITATIONS)
    if any(c.flagged for c in citations):
        notices.append(FLAGGED)
    if finish_reason == "max_tokens":
        notices.append(TRUNCATED)
    return notices


# --- M12: one question, one response --------------------------------------------------------------


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
    settings: AnswerSettings | None = None,
    document_id: uuid.UUID | None = None,
    extra_queries: list[str] | None = None,
) -> RagAnswer:
    """`extra_queries`: phrasings to search instead of making the planning call (evaluation runs
    reuse one set of phrasings across variants, so only the variant differs)."""
    started = time.perf_counter()
    timings: dict[str, float] = {}
    settings = settings or AnswerSettings(candidates, max_sources, token_budget)

    extra: list[str] = list(extra_queries or [])
    if settings.multi_query and extra_queries is None:
        t = time.perf_counter()
        _, extra, _ = plan_queries(llm, [], question, settings)
        timings["plan"] = _ms(t)
    retrieved = _retrieve(db, vectors, embedder, owner_id=owner_id, kb_id=kb_id, query=question,
                          settings=settings, extra_queries=extra,
                          document_id=document_id)  # fmt: skip
    outcome = retrieved.outcome
    timings.update(_retrieval_timings(retrieved))
    # The session keeps its pooled connection until closed, even in autocommit mode (measured:
    # 1 checked out after a SELECT, 0 after close()). Release it before waiting seconds for the
    # LLM; the session would reconnect if used again.
    db.close()
    notices = [outcome.notice] if outcome.notice else []  # e.g. "semantic search unavailable"

    if not outcome.results:
        timings["total"] = _ms(started)
        _log("Answer", question, 0, 0, True, 0, 0, None, timings)
        return RagAnswer(NOT_FOUND_ANSWER, True, notices=notices, timings_ms=timings,
                         extra_queries=extra)  # fmt: skip

    t = time.perf_counter()
    context, prompt = _prepare(outcome.results, question, settings, extra)
    timings["build_prompt"] = _ms(t)

    result = llm.generate(system=SYSTEM_PROMPT, prompt=prompt)
    timings.update(result.timings_ms)
    if result.fallback:
        notices.append(fallback_notice(result.model))
    answer = RagAnswer(
        answer="",
        not_found=False,
        notices=notices,
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        output_tokens=result.output_tokens,
        sources_given=len(context.sources),
        timings_ms=timings,
        sources=list(context.sources),
        extra_queries=extra,
    )

    if is_not_found(result.text):
        answer.answer, answer.not_found = NOT_FOUND_ANSWER, True
    else:
        resolved = resolve_citations(result.text, len(context.sources))
        answer.answer = resolved.text
        answer.invalid_citations = resolved.invalid
        answer.citations = _cited(context, resolved.order)
        notices.extend(_answer_notices(answer.citations, result.finish_reason))

    timings["total"] = _ms(started)
    _log("Answer", question, len(context.sources), sum(s.flagged for s in context.sources),
         answer.not_found, len(answer.citations), answer.invalid_citations, result,
         timings)  # fmt: skip
    return answer


# --- M13: streamed, with conversation memory ------------------------------------------------------


@dataclass(frozen=True)
class Turn:
    """Where a streamed answer belongs."""

    owner_id: uuid.UUID
    kb_id: uuid.UUID
    conversation_id: uuid.UUID
    new: bool  # the first question: the conversation is created when the turn is saved
    history: list[tuple[str, str]]  # selected earlier messages, oldest first; [] when new


def rewrite_question(llm: LLMProvider, history: list[tuple[str, str]], question: str,
                     model: str | None) -> str | None:  # fmt: skip
    """The follow-up as a standalone question, or None if the rewrite failed (the caller then
    searches the question as written). Quota and configuration errors are raised: the answer
    call would fail the same way, so there's no point going on."""
    try:
        result = llm.generate(
            system=REWRITE_SYSTEM_PROMPT,
            prompt=build_rewrite_prompt(history, question),
            model=model,
            json_schema=REWRITE_SCHEMA,
            max_output_tokens=REWRITE_MAX_OUTPUT_TOKENS,
        )
    except (QuotaExhaustedError, LLMNotConfiguredError):
        raise
    except AppError as exc:
        logger.warning("Rewrite failed (%s): searching the question as written", exc.code)
        return None
    rewritten = parse_rewrite(result.text, max_chars=REWRITE_MAX_CHARS)
    if rewritten is None:
        logger.warning("Rewrite reply unusable (%d chars): searching the question as written",
                       len(result.text))  # fmt: skip
    return rewritten


def plan_queries(
    llm: LLMProvider, history: list[tuple[str, str]], question: str, settings: AnswerSettings
) -> tuple[str | None, list[str], bool]:
    """Before retrieval: (standalone question or None, extra phrasings, failed?).

    - multi-query on: one planning call returns both (first questions too);
    - off: only a follow-up is rewritten (M13); a first question costs no call.
    A failure means "search the question as written"; quota and configuration errors are
    raised (the answer call would fail the same way)."""
    if not settings.multi_query:
        if not history:
            return None, [], False
        standalone = rewrite_question(llm, history, question, settings.rewrite_model)
        return standalone, [], standalone is None
    try:
        result = llm.generate(
            system=MULTI_QUERY_SYSTEM_PROMPT,
            prompt=build_rewrite_prompt(history, question),
            model=settings.rewrite_model,
            json_schema=MULTI_QUERY_SCHEMA,
            max_output_tokens=REWRITE_MAX_OUTPUT_TOKENS,
        )
    except (QuotaExhaustedError, LLMNotConfiguredError):
        raise
    except AppError as exc:
        logger.warning("Query planning failed (%s): searching the question as written", exc.code)
        return None, [], True
    standalone, extra = parse_search_queries(result.text, max_chars=REWRITE_MAX_CHARS)
    return standalone, extra, standalone is None and not extra


def stream_answer(
    read_sessions: SessionFactory,
    write_sessions: SessionFactory,
    vectors: VectorStore,
    embedder: Callable[[], Embedder],
    llm: LLMProvider,
    *,
    turn: Turn,
    question: str,
    settings: AnswerSettings,
    document_id: uuid.UUID | None = None,
) -> Iterator[Event]:
    """Answer a question as a stream of events (§3.3), then save the turn.

    Events: `conversation` (first question only: its new id and title), `status` (rewriting,
    retrieving, generating), `token` (text, already citation-checked), `citations`, `done`; or
    `error` instead of the rest. Nothing is saved after an error. If the reader goes away while
    the answer is being written (the Stop button), the text already shown is saved as a
    "stopped" answer: closing this generator raises GeneratorExit at the pending `yield`.
    """
    started = time.perf_counter()
    timings: dict[str, float] = {}
    notices: list[str] = []
    shown: list[str] = []  # the answer text as sent to the reader
    saved = False
    rewritten: str | None = None
    context: Context | None = None
    cites: CitationStream | None = None
    result: LLMResult | None = None

    def save(content: str, outcome: str, citations: list[Citation]) -> uuid.UUID:
        nonlocal saved
        timings["total"] = _ms(started)
        record = conversations.AnswerRecord(
            content=content,
            outcome=outcome,
            citations=[c.snapshot() for c in citations],
            notices=list(notices),
            model=result.model if result else None,
            prompt_tokens=result.prompt_tokens if result else None,
            output_tokens=result.output_tokens if result else None,
            prompt_version=PROMPT_VERSION if result else None,
            latency_ms=dict(timings),
        )
        with write_sessions() as db:
            message_id = conversations.save_turn(
                db, owner_id=turn.owner_id, kb_id=turn.kb_id,
                conversation_id=turn.conversation_id, new=turn.new, question=question,
                rewritten_query=rewritten, answer=record,
            )  # fmt: skip
        saved = True
        return message_id

    def done(message_id: uuid.UUID, answer: str, not_found: bool,
             citations: list[Citation]) -> dict[str, Any]:  # fmt: skip
        return {
            "message_id": str(message_id),
            "conversation_id": str(turn.conversation_id),
            "answer": answer,
            "not_found": not_found,
            "notices": notices,
            "model": result.model if result else None,
            "prompt_tokens": result.prompt_tokens if result else None,
            "output_tokens": result.output_tokens if result else None,
            "sources_given": len(context.sources) if context else 0,
            "invalid_citations": cites.resolver.invalid if cites else 0,
            "prompt_version": PROMPT_VERSION,
            "rewritten_query": rewritten,
            "citation_count": len(citations),
            "timings_ms": timings,
        }

    try:
        if turn.new:
            yield "conversation", {"id": str(turn.conversation_id),
                                   "title": conversations.title_from(question)}  # fmt: skip

        query = question
        extra: list[str] = []
        if turn.history or settings.multi_query:
            # "rewriting" = a follow-up being made standalone; "planning" = phrasings only
            yield "status", {"stage": "rewriting" if turn.history else "planning"}
            t = time.perf_counter()
            standalone, extra, failed = plan_queries(llm, turn.history, question, settings)
            timings["rewrite" if turn.history else "plan"] = _ms(t)
            if failed and turn.history:
                notices.append(REWRITE_FAILED)
            elif standalone and standalone.casefold() != question.casefold():
                rewritten = query = standalone

        yield "status", {"stage": "retrieving", "query": rewritten}
        with read_sessions() as db:  # closed (connection released) before the LLM call
            retrieved = _retrieve(db, vectors, embedder, owner_id=turn.owner_id,
                                  kb_id=turn.kb_id, query=query, settings=settings,
                                  extra_queries=extra, document_id=document_id)  # fmt: skip
        outcome = retrieved.outcome
        timings.update(_retrieval_timings(retrieved))
        if outcome.notice:
            notices.append(outcome.notice)

        if not outcome.results:
            message_id = save(NOT_FOUND_ANSWER, "not_found", [])
            _log("Streamed answer", question, 0, 0, True, 0, 0, None, timings)
            yield "citations", []
            yield "done", done(message_id, NOT_FOUND_ANSWER, True, [])
            return

        t = time.perf_counter()
        context, prompt = _prepare(outcome.results, query, settings, extra)
        timings["build_prompt"] = _ms(t)

        yield "status", {"stage": "generating"}
        gate, cites = NotFoundGate(), CitationStream(len(context.sources))
        stream = llm.stream(system=SYSTEM_PROMPT, prompt=prompt)
        try:
            for piece in stream:
                if isinstance(piece, LLMResult):
                    result = piece
                    continue
                if text := cites.feed(gate.feed(piece)):
                    shown.append(text)
                    yield "token", {"text": text}
        finally:
            stream.close()  # on Stop: ends the Gemini response too
        if text := cites.feed(gate.finish()) + cites.finish():
            shown.append(text)
            yield "token", {"text": text}
        if result is None:
            raise RuntimeError("The LLM stream ended without its result")
        timings.update(result.timings_ms)
        if result.fallback:
            notices.append(fallback_notice(result.model))

        if gate.state == "not_found":
            message_id = save(NOT_FOUND_ANSWER, "not_found", [])
            answer, citations, not_found = NOT_FOUND_ANSWER, [], True
        else:
            answer = "".join(shown)
            citations = _cited(context, cites.resolver.order)
            notices.extend(_answer_notices(citations, result.finish_reason))
            message_id = save(answer, "answered", citations)
            not_found = False
        _log("Streamed answer", question, len(context.sources),
             sum(s.flagged for s in context.sources), not_found, len(citations),
             cites.resolver.invalid, result, timings)  # fmt: skip
        yield "citations", [c.snapshot() for c in citations]
        yield "done", done(message_id, answer, not_found, citations)

    except GeneratorExit:
        # The reader left (Stop, closed tab). Keep what they saw of the answer, if anything.
        if shown and not saved and context is not None and cites is not None:
            try:
                save("".join(shown), "stopped", _cited(context, cites.resolver.order))
                logger.info("Answer stopped by the reader after %d chars", len("".join(shown)))
            except Exception as exc:  # noqa: BLE001 - nobody is listening any more
                logger.warning("Couldn't save the stopped answer (%s)", type(exc).__name__)
        raise
    except AppError as exc:
        logger.warning("Streamed answer failed (%s)", exc.code)
        yield "error", _error(exc.code, exc.message, getattr(exc, "retry_after", None))
    except Exception:
        logger.exception("Streamed answer crashed")
        yield "error", _error("internal_error", UNEXPECTED)


def _error(code: str, message: str, retry_after: float | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if retry_after is not None:
        body["retry_after"] = max(1, math.ceil(round(retry_after, 3)))  # like Retry-After
    return body


def _log(what, question, sources, flagged, not_found, cited, invalid, result, timings) -> None:
    logger.info(
        "%s question_chars=%d sources=%d flagged=%d not_found=%s cited=%d invalid=%d "
        "model=%s attempts=%s prompt_tokens=%s output_tokens=%s timings_ms=%s",
        what, len(question), sources, flagged, not_found, cited, invalid,
        result.model if result else None, result.attempts if result else 0,
        result.prompt_tokens if result else None, result.output_tokens if result else None,
        timings,
    )  # fmt: skip
