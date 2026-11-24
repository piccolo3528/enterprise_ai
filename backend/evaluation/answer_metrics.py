"""From per-question answer records to the M15 numbers. Pure functions (unit-tested).

A record (dict) per question, as written by run_answers.py:
    id, type, answerable, not_found, error (or None), cited, invalid, cited_relevant (of cited,
    how many overlap an expected section; None if unlabelled), judgement (or None), timings,
    prompt_tokens, output_tokens
Judgement dicts: {"claims": [{"supported", "evidence", "cited"}], "correctness", "relevance"}.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from typing import Any

from evaluation import metrics


def _claims(record: dict) -> list[dict]:
    return (record.get("judgement") or {}).get("claims") or []


def _mean_or_none(values: list[float]) -> float | None:
    return metrics.mean(values) if values else None


def citation_correct(claim: dict) -> bool | None:
    """Does a cited source state the claim? None when the claim cites nothing."""
    cited = set(claim.get("cited") or [])
    return bool(cited & set(claim.get("evidence") or [])) if cited else None


def summarize(records: Sequence[dict]) -> dict[str, Any]:
    ok = [r for r in records if not r.get("error")]
    unanswerable = [r for r in ok if not r["answerable"]]
    answerable = [r for r in ok if r["answerable"]]
    answered = [r for r in answerable if not r["not_found"]]
    judged = [r for r in ok if r.get("judgement") and not r["not_found"]]
    claims = [c for r in judged for c in _claims(r)]
    per_answer = [sum(c["supported"] for c in cs) / len(cs) for r in judged if (cs := _claims(r))]
    cited_claims = [v for c in claims if (v := citation_correct(c)) is not None]
    correctness = Counter(
        "refused" if r["not_found"] else (r.get("judgement") or {}).get("correctness", "not judged")
        for r in answerable
    )
    relevance = Counter((r.get("judgement") or {}).get("relevance", "not judged") for r in answered)
    graded = sum(n for k, n in relevance.items() if k != "not judged")
    labelled = [r for r in answered if r.get("cited_relevant") is not None and r["cited"]]
    return {
        "questions": len(records),
        "errors": len(records) - len(ok),
        "unanswerable_refused": (sum(r["not_found"] for r in unanswerable), len(unanswerable)),
        "false_refusals": (sum(r["not_found"] for r in answerable), len(answerable)),
        "judged": len(judged),
        "claims": len(claims),
        "faithfulness_claims": metrics.mean([c["supported"] for c in claims]) if claims else None,
        "faithfulness_answers": metrics.mean(per_answer) if per_answer else None,
        "fully_faithful": (sum(1 for v in per_answer if v == 1.0), len(per_answer)),
        "unsupported_claims": sum(1 for c in claims if not c["supported"]),
        "claims_with_citation": (len(cited_claims), len(claims)),
        "citation_accuracy": metrics.mean(cited_claims) if cited_claims else None,
        "invalid_citations": sum(r.get("invalid", 0) for r in ok),
        "cited_passage_precision": (
            metrics.mean([r["cited_relevant"] / r["cited"] for r in labelled]) if labelled else None
        ),
        "correctness": dict(correctness),
        "correct_rate": correctness["correct"] / len(answerable) if answerable else None,
        "relevance": dict(relevance),
        # over the answers the judge graded: an answer whose judgement failed is unknown, not "no"
        "relevance_yes_rate": relevance["yes"] / graded if graded else None,
        "not_judged": relevance["not judged"],
        "prompt_tokens": _mean_or_none([r["prompt_tokens"] for r in ok if r.get("prompt_tokens")]),
    }


def latency(records: Sequence[dict], stages=("plan", "retrieval", "generate", "total")):
    """p50/p95 per stage over the questions that have it, in ms."""
    values: dict[str, list[float]] = defaultdict(list)
    for r in records:
        timings = r.get("timings") or {}
        for stage in stages:
            if (t := timings.get(stage)) is not None:
                values[stage].append(t)
        # The evaluation's own judge calls share the rate limiter, so its queue time isn't what a
        # user would wait: the answer call's wait is subtracted here.
        if "total" in timings:
            values["total minus limiter wait"].append(
                timings["total"] - timings.get("rate_limit_wait", 0.0)
            )
    return {
        stage: {"p50": metrics.percentile(v, 50), "p95": metrics.percentile(v, 95), "n": len(v)}
        for stage, v in values.items()
    }


def by_type(records: Sequence[dict]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        if not r.get("error") and r["answerable"]:
            groups[r["type"]].append(r)
    out = {}
    for qtype, rows in sorted(groups.items()):
        s = summarize(rows)
        out[qtype] = {"n": len(rows), "correct": s["correctness"].get("correct", 0),
                      "faithfulness": s["faithfulness_claims"]}  # fmt: skip
    return out
