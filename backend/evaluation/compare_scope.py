"""M16b: what does asking across all knowledge bases cost, compared with selecting the right one?

Run from backend/ with the venv active (needs TEST_DATABASE_URL and Qdrant in backend/.env):
    python evaluation/compare_scope.py
        --multi-query evaluation/reports/2026-11-20_query_variants.json  (one command line)

The 22 corpus documents go into five knowledge bases of one owner, one per folder (finance,
governance, hr, it, operations). Every labelled question then runs through the app's own
`answer_retrieval.retrieve` with the chat's settings (cached multi-query phrasings, outdated
versions demoted) twice:
  - "right KB": only the knowledge base holding the question's expected documents (what a user
    gets by selecting it; for a question whose documents span folders, the folder holding most
    of them, so that case shows what selecting one KB loses);
  - "all KBs": every knowledge base of the owner (M16b), no selection.
No Gemini or Groq calls (the phrasings are cached). Nothing is stored (see harness.py). Writes
evaluation/reports/<date>_scope.md.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_settings  # noqa: E402
from app.services.answer_retrieval import RetrievalSettings, retrieve  # noqa: E402
from app.services.embeddings import get_embedder  # noqa: E402
from app.services.ingestion.tokens import get_tokens  # noqa: E402
from evaluation import analysis, metrics  # noqa: E402
from evaluation.harness import (  # noqa: E402
    REPORTS_DIR,
    Answer,
    ChunkingConfig,
    Hit,
    Index,
    Variant,
    build_index,
    evaluation_session,
    load_questions,
)
from evaluation.run_eval import multi_version_docs, pct  # noqa: E402

CHAT = RetrievalSettings(version_mode="demote")  # the app's defaults (D73, D75)
NOISE_POINTS = 2  # 50 scored questions: one question = 2 points (L49)


def right_folder(question, index: Index) -> tuple[str | None, bool]:
    """(the folder to search when the user selects "the right KB", whether the expected
    documents span several folders)."""
    folders = Counter(index.folder_of_document[d] for d in question.expected_documents
                      if d in index.folder_of_document)  # fmt: skip
    if not folders:
        return None, False
    best = sorted(folders.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return best, len(folders) > 1


def ask(db, vectors, embedder, index: Index, question, kb_id,
        extra) -> tuple[Answer, set[str]]:  # fmt: skip
    got = retrieve(
        db, vectors, lambda: embedder, None, owner_id=index.owner_id, kb_id=kb_id,
        query=question.text, settings=CHAT, extra_queries=extra,
    )  # fmt: skip
    hits = [
        Hit(
            chunk_id=r.passage.chunk_id,
            score=r.score,
            units=index.units[r.passage.chunk_id],
            version=index.version_of[r.passage.chunk_id],
            tokens=index.tokens[r.passage.chunk_id],
            semantic_score=r.semantic_score,
        )
        for r in got.outcome.results
    ]
    kbs = {str(r.passage.kb_name) for r in got.outcome.results}
    return Answer(question, Variant("hybrid"), hits, got.timings_ms), kbs


def first_rank(answer: Answer, k: int = 10) -> int | None:
    return metrics.first_relevant_rank(
        [h.units for h in answer.hits], set(answer.question.relevant), k
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--multi-query", type=Path, required=True,
        help="JSON {question_id: [phrasings]} (cached; no Gemini calls)",
    )  # fmt: skip
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    settings = load_settings()
    questions = [q for q in load_questions() if q.answerable and q.relevant]
    phrasings = json.loads(args.multi_query.read_text(encoding="utf-8"))
    embedder = get_embedder(settings.embedding_model)
    tokens = get_tokens(settings.embedding_model)

    started = time.perf_counter()
    rows = []
    results: dict[str, list[Answer]] = {"right KB": [], "all KBs": []}
    with evaluation_session(settings) as (db, vectors):
        index = build_index(db, vectors, embedder, tokens, ChunkingConfig("heading", 400, 60),
                            split_by_folder=True)  # fmt: skip
        for q in questions[:3]:  # warm-up: connections, model (not timed)
            ask(db, vectors, embedder, index, q, None, phrasings.get(q.id, []))
        for q in questions:
            folder, spans = right_folder(q, index)
            extra = phrasings.get(q.id, [])
            scoped, _ = ask(db, vectors, embedder, index, q, index.kb_of_folder[folder], extra)
            everything, kbs = ask(db, vectors, embedder, index, q, None, extra)
            results["right KB"].append(scoped)
            results["all KBs"].append(everything)
            rows.append((q, folder, spans, first_rank(scoped), first_rank(everything), kbs))
            print(f"{q.id} {folder:11s} {'spans ' if spans else '      '}"
                  f"right KB rank {first_rank(scoped)} | all KBs rank {first_rank(everything)}",
                  flush=True)  # fmt: skip

    multi = multi_version_docs(index)
    summaries = {name: analysis.summarize(answers, multi) for name, answers in results.items()}
    latency = {
        name: [a.timings_ms.get("retrieval_total", a.timings_ms.get("search", 0.0))
               for a in answers]
        for name, answers in results.items()
    }  # fmt: skip
    drop = (summaries["right KB"]["hit@1"] - summaries["all KBs"]["hit@1"]) * 100
    change = (
        f"{-drop:.0f} points higher than" if drop < 0 else f"{drop:.0f} points below"
    ) if drop else "the same as"
    verdict = (
        f"**All KBs can be the default**: Hit@1 is {change} selecting the right KB (a drop of at "
        f"most {NOISE_POINTS} points, one question, was the rule; differences of 1-2 questions "
        "are noise)."
        if drop <= NOISE_POINTS
        else f"**Keep 'All KBs' as an option, not the default**: Hit@1 is {drop:.0f} points "
        f"below selecting the right KB (more than the {NOISE_POINTS}-point noise floor)."
    )

    lines = [
        f"# Asking across all knowledge bases vs the right one ({date.today()})",
        "",
        "Generated by `evaluation/compare_scope.py` (M16b). The corpus in 5 knowledge bases by "
        "folder; the chat's retrieval (3 cached phrasings, outdated versions demoted); "
        f"{len(questions)} scored questions. Index: {index.documents} documents, "
        f"{index.chunk_count} chunks, {', '.join(sorted(index.kb_of_folder))}.",
        "",
        verdict,
        "",
        "| Scope | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Recall@5 | MRR@10 | Old version first | "
        "p50 ms | p95 ms |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, s in summaries.items():
        stale, of = s["stale_first"]
        lines.append(
            f"| {name} | {pct(s['hit@1'])} | {pct(s['hit@3'])} | {pct(s['hit@5'])} | "
            f"{pct(s['hit@10'])} | {pct(s['recall@5'])} | {s['mrr@10']:.3f} | {stale} of {of} | "
            f"{metrics.percentile(latency[name], 50):.0f} | "
            f"{metrics.percentile(latency[name], 95):.0f} |"
        )
    changed = [r for r in rows if r[3] != r[4]]
    spanning = [r for r in rows if r[2]]
    lines += [
        "",
        f"## Questions whose first relevant rank changed ({len(changed)})",
        "",
        "| Question | Type | Right KB (folder) | Rank, right KB | Rank, all KBs "
        "| KBs in the top 10 (all) |",
        "|---|---|---|---|---|---|",
    ]
    for q, folder, spans, a, b, kbs in changed:
        lines.append(f"| {q.id} | {q.type} | {folder}{' (spans folders)' if spans else ''} | "
                     f"{a or '—'} | {b or '—'} | {len(kbs)} |")  # fmt: skip
    lines += [
        "",
        f"## Questions whose documents span folders ({len(spanning)})",
        "",
        "Selecting one knowledge base can't find the other folder's passages; searching all can.",
        "",
    ]
    for q, folder, _, a, b, _ in spanning:
        docs = ", ".join(sorted(q.expected_documents))
        lines.append(f"- {q.id} ({docs}): right KB = {folder}, rank {a or '—'}; "
                     f"all KBs rank "
                     f"{b or '—'}")  # fmt: skip
    lines += ["", f"Run time {time.perf_counter() - started:.0f} s."]
    path = REPORTS_DIR / f"{date.today()}_scope.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(verdict)
    print("report:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
