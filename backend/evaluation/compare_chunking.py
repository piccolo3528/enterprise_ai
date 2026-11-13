"""Compare chunking configurations on retrieval quality (the M8 question, answered with data).

Run from backend/ with the venv active:
    python evaluation/compare_chunking.py

For each configuration: chunk + embed the whole corpus into a fresh throwaway index, ask all
57 questions in semantic, keyword and hybrid mode (BGE prefix on), and compare.

Read the "tokens in top 5" column next to the hit rates: bigger chunks cover more sections each,
so they "hit" more easily, but they also hand the LLM more text to read (M12's context budget).
A fair comparison looks at quality *per token*, not hit rate alone.

Writes evaluation/reports/<date>_chunking_comparison.md. Nothing is stored (see harness.py).
"""

from __future__ import annotations

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
    ChunkingConfig,
    Variant,
    ask_all,
    build_index,
    evaluation_session,
    load_questions,
)
from evaluation.run_eval import multi_version_docs, pct  # noqa: E402

CONFIGS = [
    ChunkingConfig("heading", 400, 60),  # the app's default for Markdown/DOCX (auto)
    ChunkingConfig("recursive", 400, 60),  # the default for documents without headings
    ChunkingConfig("recursive", 200, 30),
    ChunkingConfig("fixed", 400, 0),
    ChunkingConfig("overlap", 400, 60),
]
MODES = [Variant("semantic"), Variant("keyword"), Variant("hybrid")]


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    settings = load_settings()
    questions = load_questions()
    embedder = get_embedder(settings.embedding_model)
    tokens = get_tokens(settings.embedding_model)

    rows = []
    started = time.perf_counter()
    with evaluation_session(settings) as (db, vectors):
        for config in CONFIGS:
            index = build_index(db, vectors, embedder, tokens, config)
            multi = multi_version_docs(index)
            mean_tokens = sum(index.tokens.values()) / index.chunk_count
            print(f"{config.name}: {index.chunk_count} chunks, mean {mean_tokens:.0f} tokens, "
                  f"embedded in {index.seconds['embed']:.0f} s")  # fmt: skip
            for variant in MODES:
                answers = ask_all(db, vectors, embedder, index, questions, variant,
                                  candidates=settings.retrieval_top_k)  # fmt: skip
                s = analysis.summarize(answers, multi)
                rows.append((config, index.chunk_count, mean_tokens, variant.name, s))
                print(f"  {variant.name:8} hit@5 {pct(s['hit@5'])}  recall@5 {pct(s['recall@5'])}"
                      f"  mrr {s['mrr@10']:.3f}  tokens@5 {s['tokens@5']:.0f}")  # fmt: skip

    lines = [
        "# Chunking comparison",
        "",
        f"Date {date.today().isoformat()} · 22 documents · 50 scored questions · "
        f"run took {time.perf_counter() - started:.0f} s. Same relevance rule as run_eval.py.",
        "",
        "| Chunking | Chunks | Mean tokens | Mode | Hit@1 | Hit@5 | Recall@5 | Recall@10 "
        "| MRR@10 | Precision@5 | Tokens in top 5 | Old version first |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for config, chunks, mean_tokens, mode, s in rows:
        stale, of = s["stale_first"]
        lines.append(
            f"| {config.name} | {chunks} | {mean_tokens:.0f} | {mode} | {pct(s['hit@1'])} "
            f"| {pct(s['hit@5'])} | {pct(s['recall@5'])} | {pct(s['recall@10'])} "
            f"| {s['mrr@10']:.3f} | {pct(s['precision@5'])} | {s['tokens@5']:.0f} "
            f"| {stale} of {of} |"
        )
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"{date.today().isoformat()}_chunking_comparison.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
