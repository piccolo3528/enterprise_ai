"""M15: evaluate answers end to end with the real Gemini, and judge them.

Run from backend/ with the venv active (needs TEST_DATABASE_URL, Qdrant, GEMINI_API_KEY):
    python evaluation/run_answers.py                         # the app as configured (rank order)
    python evaluation/run_answers.py --variants rank sandwich compress

Every question goes through `rag.answer_question` exactly as /ask runs it (multi-query planning,
version rule, 10 sources, the answer prompt), on the heading-aware 400/60 index (rolled back,
harness.py). The first variant makes the real planning call and records its phrasings; later
variants reuse them, so only the context differs. Each answer is then judged (judge.py, cached).

Calls: ~2 per question for the first variant (planning + answer), 1 for the others, plus one
judge call per answer that isn't cached. Writes evaluation/reports/<date>_answers.md (+ .json,
which keeps every judge prompt: `--rejudge <json>` re-grades it with the current judge, without
regenerating answers).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import replace
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_settings  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.services import rag  # noqa: E402
from app.services.embeddings import get_embedder  # noqa: E402
from app.services.ingestion.tokens import get_tokens  # noqa: E402
from app.services.llm import build_chain  # noqa: E402
from app.services.llm.groq import GroqClient  # noqa: E402
from evaluation import answer_metrics, metrics  # noqa: E402
from evaluation.harness import (  # noqa: E402
    REPORTS_DIR,
    ChunkingConfig,
    build_index,
    evaluation_session,
    load_questions,
)
from evaluation.judge import (  # noqa: E402
    JUDGE_VERSION,
    JudgeCache,
    JudgeError,
    build_judge_prompt,
    judge,
    judge_client,
    judge_sources,
    patiently,
)

DATASET = Path(__file__).resolve().parent / "datasets" / "eval_dataset.json"


class KeepOpen:
    """The harness's rows are only flushed, never committed: rag's db.close() would roll them
    back (L58). Closing is a no-op here."""

    def __init__(self, session):
        self._session = session

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._session, name)


def variant_settings(base: rag.AnswerSettings, name: str, tokens) -> rag.AnswerSettings:
    if name == "rank":
        return base
    if name == "sandwich":
        return replace(base, context_order="sandwich")
    if name == "compress":
        return replace(base, compress=True, tokens=tokens)
    raise SystemExit(f"unknown variant {name!r}")


def judge_prompt_for(question, reference, a: rag.RagAnswer) -> str:
    cited_ids = [c.result.passage.chunk_id for c in a.citations]
    by_id = {s.result.passage.chunk_id: s for s in a.sources}
    cited = [by_id[i].prompt_input() for i in cited_ids if i in by_id]
    others = [s.prompt_input() for s in a.sources if s.result.passage.chunk_id not in cited_ids]
    expected, notes = reference["expected_answer"], reference.get("grading_notes", "")
    return build_judge_prompt(judge_sources(cited, others), question.text, a.answer,
                              expected, notes)  # fmt: skip


def judge_row(row: dict, llm, model: str, cache: JudgeCache) -> None:
    """Judge (or re-judge) a row from its stored prompt; failures are recorded, not raised."""
    row["judgement"], row.pop("judge_error", None)
    try:
        j = judge(llm, model, row["judge_prompt"], cache)
    except (AppError, JudgeError) as exc:
        row["judgement"], row["judge_error"] = None, getattr(exc, "code", str(exc))
        return
    row["judgement"] = {
        "claims": [{"claim": c.text, "supported": c.supported, "evidence": list(c.evidence),
                    "cited": list(c.cited)} for c in j.claims],
        "correctness": j.correctness, "relevance": j.relevance, "reason": j.reason,
        "cached": j.cached, "judge": JUDGE_VERSION,
    }  # fmt: skip


def rejudge(path: Path) -> Path:
    """Re-grade a saved run with the current judge: no answer is regenerated."""
    settings = load_settings()
    judge_llm = judge_client(settings)
    cache = JudgeCache.load()
    results = json.loads(path.read_text(encoding="utf-8"))
    started = time.perf_counter()
    for name, rows in results.items():
        for row in rows:
            if row.get("judge_prompt"):
                judge_row(row, judge_llm, judge_llm.model, cache)
                print(name, row["id"], (row["judgement"] or {}).get("correctness"), flush=True)
    which = path.stem.partition("_answers_")[2] or "primary"
    model = next((r["model"] for rows in results.values() for r in rows if r.get("model")), "?")
    label = f"{which}: {model}, re-judged"
    # the run's own file name (and date), so a re-grade replaces its report instead of copying it
    return write_report(results, time.perf_counter() - started, settings, label,
                        path.with_suffix(".md"))  # fmt: skip


def answering_model(settings, which: str):
    """One model, never the chain: an evaluation must know which model answered."""
    chain = build_chain(settings)
    pick = {"primary": lambda: chain[0],
            "gemini-fallback": lambda: next(p for p in chain[1:] if not isinstance(p, GroqClient)),
            "groq": lambda: next(p for p in chain if isinstance(p, GroqClient))}  # fmt: skip
    try:
        return pick[which]()
    except (StopIteration, IndexError):
        raise SystemExit(f"{which!r} isn't configured in backend/.env") from None


def reusable(previous: list[dict] | None) -> dict[str, dict]:
    """Rows of an earlier (partial) run that needn't be asked again: answered, or refused.
    A row whose judgement failed keeps its answer and is only judged again."""
    return {r["id"]: r for r in previous or [] if not r.get("error")}


def run(variants: list[str], limit: int | None, which: str = "primary",
        phrasings_file: Path | None = None, resume: Path | None = None) -> Path:  # fmt: skip
    settings = load_settings()
    previous = json.loads(resume.read_text(encoding="utf-8")) if resume else {}
    questions = load_questions()[:limit] if limit else load_questions()
    reference = {
        q["question_id"]: q for q in json.loads(DATASET.read_text(encoding="utf-8"))["questions"]
    }
    embedder = get_embedder(settings.embedding_model)
    tokens = get_tokens(settings.embedding_model)
    llm = answering_model(settings, which)
    judge_llm = judge_client(settings)
    base = rag.answer_settings(settings)
    cache = JudgeCache.load()
    # Cached phrasings (M14's query_variants.json): no planning call, and the same phrasings
    # for every answering model. Without them the first variant makes the real planning call.
    cached = json.loads(phrasings_file.read_text(encoding="utf-8")) if phrasings_file else None
    phrasings: dict[str, list[str]] = dict(cached or {})
    for rows in previous.values():  # a resumed run asks the rest with the same phrasings
        phrasings.update({r["id"]: r["extra_queries"] for r in rows if "extra_queries" in r})
    results: dict[str, list[dict]] = {}
    started = time.perf_counter()
    label = f"{which}: {llm.model}" + (", cached phrasings" if cached else "")
    try:
        with evaluation_session(settings) as (db, vectors):
            index = build_index(db, vectors, embedder, tokens, ChunkingConfig("heading", 400, 60))
            for v_index, name in enumerate(variants):
                results[name] = _ask_all(
                    questions, results.setdefault(name, []), reusable(previous.get(name)),
                    db=db, vectors=vectors, embedder=embedder, llm=llm, judge_llm=judge_llm,
                    cache=cache, index=index, settings=settings, reference=reference,
                    cfg=variant_settings(base, name, tokens), name=name,
                    plan=v_index == 0 and cached is None, phrasings=phrasings,
                )  # fmt: skip
    except Exception:
        # The index lives in one uncommitted transaction: a dropped connection (the corporate
        # network did this on 2026-11-23) loses it. Keep what was answered; --resume continues.
        path = write_report(results, time.perf_counter() - started, settings, label + " (partial)")
        print("partial results saved; continue with --resume", path.with_suffix(".json"))
        raise
    return write_report(results, time.perf_counter() - started, settings, label)


def _ask_all(questions, rows, done, *, db, vectors, embedder, llm, judge_llm, cache, index,
             settings, reference, cfg, name, plan, phrasings) -> list[dict]:  # fmt: skip
    """Answer and judge each question into `rows` (filled in place, so a crash keeps them)."""
    for q in questions:
        if (old := done.get(q.id)) is not None:
            if old.get("judge_error") and old.get("judge_prompt"):
                judge_row(old, judge_llm, judge_llm.model, cache)
            rows.append(old)
            continue
        row = {"id": q.id, "type": q.type, "answerable": q.answerable, "error": None,
               "model": llm.model}  # fmt: skip
        try:
            a = patiently(lambda q=q: rag.answer_question(
                KeepOpen(db), vectors, lambda: embedder, llm,
                owner_id=index.owner_id, kb_id=index.kb_id, question=q.text,
                candidates=settings.retrieval_top_k, max_sources=settings.context_max_sources,
                token_budget=settings.context_token_budget, settings=cfg,
                extra_queries=None if plan and q.id not in phrasings else phrasings.get(q.id, []),
            ), patience=3)  # fmt: skip
        except AppError as exc:
            row["error"] = exc.code
            rows.append(row)
            print(name, q.id, "ERROR", exc.code, flush=True)
            continue
        phrasings.setdefault(q.id, a.extra_queries)  # later variants reuse the first's
        cited_units = [index.units[c.result.passage.chunk_id] for c in a.citations]
        relevant = sum(bool(metrics.matched_units(u, q.relevant)) for u in cited_units)
        row.update(
            not_found=a.not_found, answer=a.answer, cited=len(a.citations),
            invalid=a.invalid_citations, cited_relevant=relevant if q.relevant else None,
            sources_given=a.sources_given,
            context_tokens=sum(s.result.passage.token_count for s in a.sources),
            prompt_tokens=a.prompt_tokens, output_tokens=a.output_tokens,
            timings=a.timings_ms, notices=a.notices, judgement=None,
            extra_queries=phrasings[q.id],
        )  # fmt: skip
        if not a.not_found:
            row["judge_prompt"] = judge_prompt_for(q, reference[q.id], a)
            judge_row(row, judge_llm, judge_llm.model, cache)
        rows.append(row)
        j = row["judgement"]
        print(name, q.id, "NF" if a.not_found else
              f"{j['correctness'] if j else 'unjudged'} faith "
              f"{sum(c['supported'] for c in j['claims'])}/{len(j['claims'])}" if j else "",
              f"{a.timings_ms.get('total', 0):.0f}ms", flush=True)  # fmt: skip
    return rows


def judge_name(settings) -> str:
    return settings.groq_model if settings.judge_provider == "groq" else settings.gemini_model_judge


def pct(x) -> str:
    return "–" if x is None else f"{x * 100:.0f}%"


def write_report(results: dict[str, list[dict]], seconds: float, settings,
                 label: str = "primary", path: Path | None = None) -> Path:  # fmt: skip
    multi = "on" if settings.multi_query_enabled else "off"
    lines = [
        f"# Answer evaluation ({date.today().isoformat()})", "",
        f"57 labelled questions (50 answerable, 7 unanswerable) through `rag.answer_question` "
        f"answered by **{label}**, multi-query {multi}, versions "
        f"`{settings.version_mode}`, 10 sources; judged by `{judge_name(settings)}` "
        f"({JUDGE_VERSION}, validated on hand-labelled cases: `*_judge_validation.md`). Run "
        f"took {seconds / 60:.0f} min. One question is 2 points of 50: smaller differences are "
        "noise.", "",
        "**Faithfulness** = claims the judge found stated by the sources / all claims. "
        "**Citation accuracy** = cited claims whose citation includes a supporting source. "
        "**Correct** = the judge's verdict against the dataset's reference answer.", "",
        "## Summary", "",
        "| Variant | Unanswerable refused | False refusals | Correct | Partial | Incorrect | "
        "Faithfulness (claims) | Fully faithful answers | Citation accuracy | Cited passages "
        "relevant | Invalid citations | Relevance yes | Context tokens | Answer time p50 / p95 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]  # fmt: skip
    for name, rows in results.items():
        s = answer_metrics.summarize(rows)
        lat = answer_metrics.latency(rows).get("total minus limiter wait", {})
        c = s["correctness"]
        sizes = [r["context_tokens"] for r in rows if r.get("context_tokens")]
        ctx = metrics.mean(sizes) if sizes else 0
        lines.append(
            f"| {name} | {s['unanswerable_refused'][0]} of {s['unanswerable_refused'][1]} | "
            f"{s['false_refusals'][0]} of {s['false_refusals'][1]} | {c.get('correct', 0)} | "
            f"{c.get('partial', 0)} | {c.get('incorrect', 0)} | {pct(s['faithfulness_claims'])} "
            f"({s['claims'] - s['unsupported_claims']} of {s['claims']}) | "
            f"{s['fully_faithful'][0]} of {s['fully_faithful'][1]} | "
            f"{pct(s['citation_accuracy'])} | "
            f"{pct(s['cited_passage_precision'])} | {s['invalid_citations']} | "
            f"{pct(s['relevance_yes_rate'])} | {ctx:.0f} | "
            f"{lat.get('p50', 0) / 1000:.1f} / {lat.get('p95', 0) / 1000:.1f} s |"
        )
        if s["errors"]:
            note = f"↳ {name}: {s['errors']} questions failed (LLM errors) and are excluded"
            lines.append(f"| {note} |" + " |" * 13)
        if s["not_judged"]:
            note = (f"↳ {name}: {s['not_judged']} answers not judged yet (judge quota): "
                    "excluded from correctness, faithfulness and relevance; `--rejudge` fills them")
            lines.append(f"| {note} |" + " |" * 13)
    first = next(iter(results))
    lines += [
        "",
        f"## Latency by stage ({first}, ms)",
        "",
        "The app's Gemini rate limiter (10 calls a minute) also queues the evaluation's "
        "back-to-back questions, so `plan` and `total` include queue time a lone user wouldn't "
        "have; `total minus limiter wait` removes the answer call's wait (the planning call's "
        "wait can't be separated). Free-tier Gemini latency varies: a slow call is the model, "
        "not the pipeline.",
        "",
        "| Stage | p50 | p95 | n |",
        "|---|---|---|---|",
    ]
    for stage, v in answer_metrics.latency(results[first]).items():
        lines.append(f"| {stage} | {v['p50']:.0f} | {v['p95']:.0f} | {v['n']} |")
    lines += [
        "",
        "## By question type (correct of n / faithfulness)",
        "",
        "| Type | n | " + " | ".join(results) + " |",
        "|---|---|" + "---|" * len(results),
    ]
    types = {name: answer_metrics.by_type(rows) for name, rows in results.items()}
    for qtype, row in types[first].items():
        cells = [
            f"{types[n][qtype]['correct']} / {pct(types[n][qtype]['faithfulness'])}"
            for n in results
        ]
        lines.append(f"| {qtype} | {row['n']} | " + " | ".join(cells) + " |")
    for name, rows in results.items():
        lines += ["", f"## Answers to read: {name} (not correct, or with unsupported claims)", ""]
        for r in rows:
            j = r.get("judgement")
            if r.get("error"):
                lines.append(f"- **{r['id']}** error: {r['error']}")
            elif r["answerable"] and r["not_found"]:
                lines.append(f"- **{r['id']}** ({r['type']}) refused (false refusal)")
            elif not r["answerable"] and not r["not_found"]:
                lines.append(f"- **{r['id']}** (unanswerable) answered: {r['answer'][:160]}")
            elif j and (
                j["correctness"] != "correct" or not all(c["supported"] for c in j["claims"])
            ):
                bad = [c["claim"] for c in j["claims"] if not c["supported"]]
                lines.append(
                    f"- **{r['id']}** ({r['type']}) {j['correctness']}: {j['reason']}"
                    + (f" Unsupported: {bad}" if bad else "")
                )
    if path is None:
        suffix = "" if label.startswith("primary") else "_" + label.split(":")[0]
        path = REPORTS_DIR / f"{date.today().isoformat()}_answers{suffix}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.with_suffix(".json").write_text(
        json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--variants", nargs="+", default=["rank"],
                        choices=["rank", "sandwich", "compress"])  # fmt: skip
    parser.add_argument("--limit", type=int, help="only the first N questions (a smoke run)")
    parser.add_argument("--rejudge", type=Path, help="re-grade a saved <date>_answers.json")
    parser.add_argument("--answer-model", default="primary",
                        choices=["primary", "gemini-fallback", "groq"])  # fmt: skip
    parser.add_argument("--phrasings", type=Path,
                        help="cached multi-query phrasings (skips the planning call)")
    parser.add_argument("--resume", type=Path,
                        help="an earlier (partial) run's .json: ask only what's missing")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if args.rejudge:
        print("report:", rejudge(args.rejudge))
    else:
        print("report:", run(args.variants, args.limit, args.answer_model, args.phrasings,
                             args.resume))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
