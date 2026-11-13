"""Retrieval evaluation: one chunking config, every search variant, a Markdown report.

Run from backend/ with the venv active (needs TEST_DATABASE_URL and Qdrant in backend/.env):
    python evaluation/run_eval.py                        # heading-aware 400/60 (the app default)
    python evaluation/run_eval.py --strategy recursive --size 200 --overlap 30

Writes evaluation/reports/<date>_<config>.md (+ .json with every question's results).
Nothing is stored: see harness.py.
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
from app.services.embeddings import get_embedder  # noqa: E402
from app.services.ingestion.tokens import get_tokens  # noqa: E402
from evaluation import analysis  # noqa: E402
from evaluation.harness import (  # noqa: E402
    REPORTS_DIR,
    Answer,
    ChunkingConfig,
    Index,
    Variant,
    ask_all,
    build_index,
    evaluation_session,
    load_questions,
)

VARIANTS = [
    Variant("semantic"),
    Variant("semantic", prefix=False),
    Variant("keyword"),
    Variant("hybrid"),
    Variant("hybrid", prefix=False),
]


def multi_version_docs(index: Index) -> set[str]:
    versions: dict[str, set[str]] = {}
    for label in index.version_of.values():
        versions.setdefault(analysis.document_of(label), set()).add(label)
    return {doc for doc, labels in versions.items() if len(labels) > 1}


def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def summary_table(results: dict[str, list[Answer]], multi: set[str]) -> list[str]:
    lines = [
        "| Variant | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Recall@5 | Recall@10 | Precision@5 | MRR@10 "
        "| Tokens in top 5 | Old version first |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, answers in results.items():
        s = analysis.summarize(answers, multi)
        stale, of = s["stale_first"]
        lines.append(
            f"| {name} | {pct(s['hit@1'])} | {pct(s['hit@3'])} | {pct(s['hit@5'])} "
            f"| {pct(s['hit@10'])} | {pct(s['recall@5'])} | {pct(s['recall@10'])} "
            f"| {pct(s['precision@5'])} | {s['mrr@10']:.3f} | {s['tokens@5']:.0f} "
            f"| {stale} of {of} |"
        )
    return lines


def write_report(index: Index, results: dict[str, list[Answer]], seconds: float) -> Path:
    multi = multi_version_docs(index)
    questions = next(iter(results.values()))
    n_scored = len(analysis.scored(questions))
    lines = [
        f"# Retrieval evaluation: {index.config.name}",
        "",
        f"Date {date.today().isoformat()} · {index.documents} documents · "
        f"{index.chunk_count} chunks "
        f"(mean {sum(index.tokens.values()) / index.chunk_count:.0f} tokens) · "
        f"{len(questions)} questions, {n_scored} scored (answerable, labelled with sections) · "
        f"top 10 shown, 20 candidates per retriever · run took {seconds:.0f} s "
        f"(chunk+store {index.seconds['chunk+store']:.1f} s, embed {index.seconds['embed']:.1f} s, "
        f"index {index.seconds['index']:.1f} s) · vectors in Qdrant's HNSW graph: "
        f"{index.hnsw_indexed} (0 = exact search over all vectors)",
        "",
        "Relevance: a chunk counts if its text overlaps the body of an expected section (or a "
        "subsection of it) in the expected document **and version**. *Old version first*: of "
        "the questions about a document that exists in several versions, how often an "
        "unexpected version of it came before the expected one.",
        "",
        "## Summary",
        "",
        *summary_table(results, multi),
        "",
        "## Hybrid by question type",
        "",
        "| Type | n | Hit@5 | Recall@5 | MRR@10 |",
        "|---|---|---|---|---|",
    ]
    for qtype, s in analysis.by_type(results["hybrid"]).items():
        lines.append(
            f"| {qtype} | {s['n']} | {pct(s['hit@5'])} | {pct(s['recall@5'])} | {s['mrr@10']:.3f} |"
        )

    a = analysis.answerability(results["semantic"])
    lines += [
        "",
        "## Can a similarity threshold detect unanswerable questions?",
        "",
        "Top-1 cosine similarity (semantic, with prefix):",
        "",
        "| Questions | n | min | median | max |",
        "|---|---|---|---|---|",
    ]
    for label in ("answerable", "unanswerable"):
        sp = a[label]
        lines.append(
            f"| {label} | {sp['n']} | {sp['min']:.3f} | {sp['p50']:.3f} | {sp['max']:.3f} |"
        )
    lines += [
        "",
        f"Best single threshold: {a['best_threshold']:.3f} → {pct(a['best_accuracy'])} correct, "
        f'vs {pct(a["always_answer_accuracy"])} for "always answer". Unanswerable questions\' '
        "top-1 scores: " + ", ".join(f"{qid} {s}" for qid, s in a["unanswerable_scores"]),
        "",
        "## Latency (server-side stages, ms)",
        "",
        "| Variant | total p50 | total p95 | stages p50 |",
        "|---|---|---|---|",
    ]
    for name, answers in results.items():
        lat = analysis.latency(answers)
        stages = ", ".join(f"{k} {v['p50']:.0f}" for k, v in lat.items() if k != "total")
        lines.append(
            f"| {name} | {lat['total']['p50']:.0f} | {lat['total']['p95']:.0f} | {stages} |"
        )

    lines += ["", "## Hybrid failures (nothing relevant in the top 5)", ""]
    misses = analysis.failures(results["hybrid"])
    if not misses:
        lines.append("None.")
    for m in misses:
        got = "; ".join(
            f"{h.version} {', '.join(sorted(u.split(' §')[1] for u in h.units)) or '–'}"
            for h in m.hits[:3]
        )
        lines += [
            f"- **{m.question.id}** ({m.question.type}) {m.question.text}",
            f"  - expected: {', '.join(sorted(m.question.relevant))}",
            f"  - got (top 3, sections covered): {got}",
        ]

    REPORTS_DIR.mkdir(exist_ok=True)
    slug = index.config.name.replace(" ", "_").replace("/", "-")
    path = REPORTS_DIR / f"{date.today().isoformat()}_{slug}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    raw = {
        name: [
            {
                "question_id": ans.question.id,
                "hits": [
                    {
                        "version": h.version,
                        "units": sorted(h.units),
                        "score": round(h.score, 4),
                        "tokens": h.tokens,
                    }  # fmt: skip
                    for h in ans.hits
                ],
                "timings_ms": ans.timings_ms,
            }
            for ans in answers
        ]
        for name, answers in results.items()
    }
    path.with_suffix(".json").write_text(json.dumps(raw, indent=1), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--strategy", default="heading", choices=["heading", "recursive", "fixed", "overlap"]
    )
    parser.add_argument("--size", type=int, default=400)
    parser.add_argument("--overlap", type=int, default=60)
    parser.add_argument(
        "--no-header", action="store_true", help="heading-aware chunks without the context header"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    settings = load_settings()
    config = ChunkingConfig(args.strategy, args.size, args.overlap, header=not args.no_header)
    questions = load_questions()
    print(f"Loading the embedding model and tokenizer ({settings.embedding_model})...")
    embedder = get_embedder(settings.embedding_model)
    tokens = get_tokens(settings.embedding_model)

    started = time.perf_counter()
    with evaluation_session(settings) as (db, vectors):
        index = build_index(db, vectors, embedder, tokens, config)
        print(f"Indexed {index.documents} documents -> {index.chunk_count} chunks ({config.name})")
        # Warm-up, not measured: the first searches pay for connections and the model's first
        # calls (measured: embed p50 92 ms in the first variant vs ~37 ms afterwards).
        for variant in (Variant("semantic"), Variant("keyword")):
            ask_all(db, vectors, embedder, index, questions[:5], variant)
        results = {}
        for variant in VARIANTS:
            t = time.perf_counter()
            results[variant.name] = ask_all(db, vectors, embedder, index, questions, variant,
                                            candidates=settings.retrieval_top_k)  # fmt: skip
            print(
                f"  {variant.name}: {len(questions)} questions in {time.perf_counter() - t:.0f} s"
            )
        report = write_report(index, results, time.perf_counter() - started)
    print(f"Report: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
