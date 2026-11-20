"""M14: measure each retrieval technique against the M11 baseline, alone and combined.

Run from backend/ with the venv active (needs TEST_DATABASE_URL and Qdrant in backend/.env):
    python evaluation/compare_retrieval.py
    python evaluation/compare_retrieval.py --multi-query reports/<date>_query_variants.json

Every variant runs the app's own `answer_retrieval.retrieve` over the 57 labelled questions on
the heading-aware 400/60 index (the app default). Nothing is stored (see harness.py). Writes
evaluation/reports/<date>_retrieval_techniques.md (+ .json).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_settings  # noqa: E402
from app.services.answer_retrieval import RetrievalSettings, retrieve  # noqa: E402
from app.services.embeddings import get_embedder  # noqa: E402
from app.services.ingestion.tokens import get_tokens  # noqa: E402
from app.services.reranker import get_reranker  # noqa: E402
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

BASE = RetrievalSettings(candidates=20, pool=10, max_sources=10)
OVERLAP_TOKENS = 60  # heading 400/60: neighbouring chunks of a section share up to this much
adjacency: list[int] = []  # per question of the variant being run: adjacent chunk pairs
VARIANTS: dict[str, RetrievalSettings] = {
    "baseline (hybrid, M11)": BASE,
    "rerank pool 20": RetrievalSettings(pool=20, rerank=True),
    "rerank pool 30": RetrievalSettings(pool=30, rerank=True),
    "rerank pool 50": RetrievalSettings(candidates=50, pool=50, rerank=True),
    "versions: demote": RetrievalSettings(version_mode="demote"),
    "versions: filter": RetrievalSettings(version_mode="filter"),
    "amendments": RetrievalSettings(amendments=True),
    "rerank 20 + demote": RetrievalSettings(pool=20, rerank=True, version_mode="demote"),
    "rerank 20 + demote + amendments": RetrievalSettings(
        pool=20, rerank=True, version_mode="demote", amendments=True
    ),
    "demote + amendments (no rerank)": RetrievalSettings(version_mode="demote", amendments=True),
    "rerank 20 fused with hybrid (RRF)": RetrievalSettings(
        pool=20, rerank=True, rerank_fusion=True
    ),
    "fused rerank + demote + amendments": RetrievalSettings(
        pool=20, rerank=True, rerank_fusion=True, version_mode="demote", amendments=True
    ),
}


def run_variant(
    db, vectors, embedder, reranker, index: Index, questions, settings,
    variants_for: dict[str, list[str]] | None = None,
) -> tuple[list[Answer], list]:  # fmt: skip
    answers, scores = [], []
    adjacency.clear()
    for q in questions:
        extra = (variants_for or {}).get(q.id, [])
        got = retrieve(
            db, vectors, lambda: embedder, (lambda: reranker) if settings.rerank else None,
            owner_id=index.owner_id, kb_id=index.kb_id, query=q.text, settings=settings,
            extra_queries=extra,
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
        answers.append(Answer(q, Variant("hybrid"), hits, got.timings_ms))
        spots = {(r.passage.document_id, r.passage.chunk_index) for r in got.outcome.results}
        pairs = sum(1 for doc, i in spots if (doc, i + 1) in spots)
        adjacency.append(pairs)
        if settings.rerank:
            for r in got.outcome.results:
                relevant = bool(metrics.matched_units(index.units[r.passage.chunk_id], q.relevant))
                scores.append((q.id, q.answerable, relevant, r.rerank_score,
                               index.tokens[r.passage.chunk_id]))  # fmt: skip
    return answers, scores


def threshold_table(scores) -> list[str]:
    """If passages scoring below t were dropped from the context: what is lost, what is saved."""
    labelled = [s for s in scores if s[3] is not None]
    rel = [s for s in labelled if s[2]]
    lines = ["| Drop passages scoring below | Relevant passages lost | Irrelevant dropped | "
             "Tokens saved per question |", "|---|---|---|---|"]  # fmt: skip
    questions = len({s[0] for s in labelled})
    for t in (-10.0, -8.0, -6.0, -4.0, -2.0, 0.0):
        lost = sum(1 for s in rel if s[3] < t)
        irrelevant = [s for s in labelled if not s[2]]
        dropped = sum(1 for s in irrelevant if s[3] < t)
        saved = sum(s[4] for s in labelled if s[3] < t) / max(1, questions)
        lines.append(f"| {t:g} | {lost} of {len(rel)} | {dropped} of {len(irrelevant)} | "
                     f"{saved:.0f} |")  # fmt: skip
    return lines


def write_report(index: Index, results, latencies, scores, seconds: float, adjacent) -> Path:
    multi = multi_version_docs(index)
    lines = [
        "# Retrieval techniques (M14)",
        "",
        f"Date {date.today().isoformat()} · {index.documents} documents · {index.chunk_count} "
        f"chunks (heading 400/60) · 57 questions, 50 scored · top 10 kept (the context gets 10 "
        f"sources) · run took {seconds:.0f} s",
        "",
        "Same relevance rules as M11: a chunk counts if it overlaps an expected section of the "
        "expected document **and version**. *Old version first* counts questions about a "
        "multi-version document where an unexpected version came before the expected one. "
        "*Amendments R@5*: Recall@5 on the 6 `amendment_combination` questions. Latency is "
        "server-side retrieval (search + every stage), p50/p95 over the 57 questions, after "
        "a warm-up.",
        "",
        "## Summary",
        "",
        "| Variant | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Recall@5 | Recall@10 | MRR@10 "
        "| Old version first | Amendments R@5 | Tokens in top 10 | Latency p50 / p95 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, answers in results.items():
        s = analysis.summarize(answers, multi)
        types = analysis.by_type(answers)
        rows = analysis.scored(answers)
        tokens10 = metrics.mean([sum(h.tokens for h in a.hits[:10]) for a in rows])
        lat = latencies[name]
        lines.append(
            f"| {name} | {pct(s['hit@1'])} | {pct(s['hit@3'])} | {pct(s['hit@5'])} | "
            f"{pct(s['hit@10'])} | {pct(s['recall@5'])} | {pct(s['recall@10'])} | "
            f"{s['mrr@10']:.3f} | {s['stale_first'][0]} of {s['stale_first'][1]} | "
            f"{pct(types.get('amendment_combination', {}).get('recall@5', 0))} | {tokens10:.0f} | "
            f"{lat['p50']:.0f} / {lat['p95']:.0f} ms |"
        )
    lines +=["", "## By question type (Recall@5 / MRR@10)", ""]
    names = list(results)
    lines.append("| Type | n | " + " | ".join(names) + " |")
    lines.append("|---|---|" + "---|" * len(names))
    types0 = analysis.by_type(results[names[0]])
    for qtype, row in types0.items():
        cells = []
        for name in names:
            t = analysis.by_type(results[name])[qtype]
            cells.append(f"{pct(t['recall@5'])} / {t['mrr@10']:.2f}")
        lines.append(f"| {qtype} | {row['n']} | " + " | ".join(cells) + " |")
    lines += ["", "## Adjacent chunks in the top 10 (would merging them save tokens?)", "",
              "| Variant | Questions with an adjacent pair | Pairs | Duplicate tokens at most |",
              "|---|---|---|---|"]
    for name, pairs in adjacent.items():
        lines.append(f"| {name} | {sum(1 for p in pairs if p)} of {len(pairs)} | {sum(pairs)} | "
                     f"{sum(pairs) * OVERLAP_TOKENS} (≤ {OVERLAP_TOKENS} per pair) |")
    if scores:
        lines += ["", "## A rerank-score threshold for the context? (rerank pool 20, top 10)", ""]
        lines += threshold_table(scores)
    for name in names:
        fails = analysis.failures(results[name])
        lines += ["", f"## Failures: {name} (nothing relevant in the top 5)", ""]
        items = [f"- **{a.question.id}** ({a.question.type}) {a.question.text}" for a in fails]
        lines += items or ["- none"]
    path = REPORTS_DIR / f"{date.today().isoformat()}_retrieval_techniques.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    raw = {
        name: [
            {"id": a.question.id, "hits": [[h.version, sorted(h.units)] for h in a.hits],
             "timings_ms": a.timings_ms}
            for a in answers
        ]
        for name, answers in results.items()
    }  # fmt: skip
    path.with_suffix(".json").write_text(json.dumps(raw, indent=1), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--multi-query", type=Path, help="JSON {question_id: [phrasings]}")
    parser.add_argument("--only", nargs="*", help="run only these variant names")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    settings = load_settings()
    questions = load_questions()
    embedder = get_embedder(settings.embedding_model)
    reranker = get_reranker(settings.reranker_model)
    tokens = get_tokens(settings.embedding_model)
    variants = dict(VARIANTS)
    variants_for = None
    if args.multi_query:
        variants_for = json.loads(args.multi_query.read_text(encoding="utf-8"))
        variants["multi-query (3 phrasings)"] = BASE
        variants["multi-query + demote"] = RetrievalSettings(version_mode="demote")
        variants["multi-query + rerank 20 + demote + amendments"] = RetrievalSettings(
            pool=20, rerank=True, version_mode="demote", amendments=True
        )
    if args.only:
        variants = {k: v for k, v in variants.items() if k in args.only}

    started = time.perf_counter()
    with evaluation_session(settings) as (db, vectors):
        index = build_index(db, vectors, embedder, tokens, ChunkingConfig("heading", 400, 60))
        # warm-up: connections, both models (not timed)
        reranker.score("warm up", ["warm up"])
        run_variant(db, vectors, embedder, reranker, index, questions[:3],
                    RetrievalSettings(pool=20, rerank=True, amendments=True))  # fmt: skip
        results, latencies, scores, adjacent = {}, {}, [], {}
        for name, cfg in variants.items():
            mq = variants_for if "multi-query" in name else None
            answers, s = run_variant(db, vectors, embedder, reranker, index, questions, cfg, mq)
            results[name] = answers
            totals = [a.timings_ms.get("retrieval_total", 0.0) for a in answers]
            latencies[name] = {"p50": metrics.percentile(totals, 50),
                               "p95": metrics.percentile(totals, 95)}  # fmt: skip
            if name == "rerank pool 20":
                scores = s
            adjacent[name] = list(adjacency)
            summary = analysis.summarize(answers, multi_version_docs(index))
            print(f"{name:48s} hit@1 {pct(summary['hit@1']):>4} recall@5 "
                  f"{pct(summary['recall@5']):>4} mrr {summary['mrr@10']:.3f} "
                  f"p50 {latencies[name]['p50']:.0f} ms", flush=True)  # fmt: skip
    path = write_report(index, results, latencies, scores, time.perf_counter() - started, adjacent)
    print("report:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
