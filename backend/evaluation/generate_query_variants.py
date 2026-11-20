"""M14 multi-query experiment: ask Gemini for alternative phrasings of each labelled question,
once, and save them, so compare_retrieval.py can measure multi-query without spending quota on
every run. 57 Gemini calls (utility model, JSON mode), paced by the app's rate limiter.

    python evaluation/generate_query_variants.py   ->  evaluation/reports/<date>_query_variants.json
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_settings  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.services.llm import build_llm  # noqa: E402
from app.services.llm.prompts import (  # noqa: E402
    MULTI_QUERY_SCHEMA,
    MULTI_QUERY_SYSTEM_PROMPT,
    build_rewrite_prompt,
    parse_search_queries,
)
from evaluation.harness import REPORTS_DIR, load_questions  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    settings = load_settings()
    llm = build_llm(settings)
    if llm is None:
        raise SystemExit("GEMINI_API_KEY is not set")
    out: dict[str, list[str]] = {}
    failed = 0
    started = time.perf_counter()
    for q in load_questions():
        try:
            result = llm.generate(
                system=MULTI_QUERY_SYSTEM_PROMPT,
                prompt=build_rewrite_prompt([], q.text),
                model=settings.gemini_model_utility,
                json_schema=MULTI_QUERY_SCHEMA,
                max_output_tokens=300,
            )
            out[q.id] = parse_search_queries(result.text, max_chars=1000)[1]
        except AppError as exc:
            failed += 1
            print(q.id, "failed:", exc.code, flush=True)
            out[q.id] = []
        print(q.id, out[q.id], flush=True)
    path = REPORTS_DIR / f"{date.today().isoformat()}_query_variants.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(out)} questions, {failed} failed, {time.perf_counter() - started:.0f} s -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
