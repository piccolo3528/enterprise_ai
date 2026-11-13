"""From raw answers to the numbers in the reports. Pure functions (unit-tested)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from evaluation import metrics
from evaluation.harness import Answer

KS = (1, 3, 5, 10)


def scored(answers: Sequence[Answer]) -> list[Answer]:
    """Questions retrieval can be scored on: answerable and labelled with sections."""
    return [a for a in answers if a.question.answerable and a.question.relevant]


def document_of(version: str) -> str:
    return version.rsplit(" v", 1)[0]  # "NX-HR-002 v3.0" -> "NX-HR-002"


def stale_first(answer: Answer, multi_version_docs: set[str]) -> bool | None:
    """Did an unexpected version of an expected document come before any expected version?
    None when the question can't have that problem (no expected document has several versions).
    E.g. the first NX-HR-002 chunk is from v2.0 while the answer is in v3.0."""
    if not answer.question.expected_documents & multi_version_docs:
        return None
    for hit in answer.hits:
        if document_of(hit.version) in answer.question.expected_documents:
            return hit.version not in answer.question.expected_versions
    return False


def summarize(answers: Sequence[Answer], multi_version_docs: set[str]) -> dict[str, Any]:
    rows = scored(answers)
    covered = [[h.units for h in a.hits] for a in rows]
    relevant = [set(a.question.relevant) for a in rows]
    out: dict[str, Any] = {"questions": len(rows)}
    for k in KS:
        out[f"hit@{k}"] = metrics.mean(
            [metrics.hit_at_k(c, r, k) for c, r in zip(covered, relevant, strict=True)]
        )
    for k in (5, 10):
        out[f"recall@{k}"] = metrics.mean(
            [metrics.recall_at_k(c, r, k) for c, r in zip(covered, relevant, strict=True)]
        )
    out["precision@5"] = metrics.mean(
        [metrics.precision_at_k(c, r, 5) for c, r in zip(covered, relevant, strict=True)]
    )
    out["mrr@10"] = metrics.mean(
        [metrics.reciprocal_rank(c, r, 10) for c, r in zip(covered, relevant, strict=True)]
    )
    out["tokens@5"] = metrics.mean([sum(h.tokens for h in a.hits[:5]) for a in rows])
    stale = [s for a in rows if (s := stale_first(a, multi_version_docs)) is not None]
    out["stale_first"] = (sum(stale), len(stale))
    return out


def by_type(answers: Sequence[Answer]) -> dict[str, dict[str, float]]:
    groups: dict[str, list[Answer]] = defaultdict(list)
    for a in scored(answers):
        groups[a.question.type].append(a)
    result = {}
    for qtype, items in sorted(groups.items()):
        covered = [[h.units for h in a.hits] for a in items]
        relevant = [set(a.question.relevant) for a in items]
        pairs = list(zip(covered, relevant, strict=True))
        result[qtype] = {
            "n": len(items),
            "hit@5": metrics.mean([metrics.hit_at_k(c, r, 5) for c, r in pairs]),
            "recall@5": metrics.mean([metrics.recall_at_k(c, r, 5) for c, r in pairs]),
            "mrr@10": metrics.mean([metrics.reciprocal_rank(c, r, 10) for c, r in pairs]),
        }
    return result


def failures(answers: Sequence[Answer], k: int = 5) -> list[Answer]:
    """Scored questions with nothing relevant in the top k."""
    return [
        a for a in scored(answers)
        if not metrics.hit_at_k([h.units for h in a.hits], set(a.question.relevant), k)
    ]  # fmt: skip


def answerability(semantic_answers: Sequence[Answer]) -> dict[str, Any]:
    """Can the best cosine similarity tell answerable from unanswerable questions?"""

    def top(a: Answer) -> float:
        return a.hits[0].semantic_score if a.hits and a.hits[0].semantic_score is not None else 0.0

    yes = [top(a) for a in semantic_answers if a.question.answerable]
    no = [top(a) for a in semantic_answers if not a.question.answerable]
    threshold, accuracy = metrics.best_threshold(yes, no)
    return {
        "answerable": _spread(yes),
        "unanswerable": _spread(no),
        "best_threshold": threshold,
        "best_accuracy": accuracy,
        "always_answer_accuracy": len(yes) / (len(yes) + len(no)),
        "unanswerable_scores": sorted(
            (
                (a.question.id, round(top(a), 3))
                for a in semantic_answers
                if not a.question.answerable
            ),
            key=lambda pair: -pair[1],
        ),
    }


def latency(answers: Sequence[Answer]) -> dict[str, dict[str, float]]:
    stages: dict[str, list[float]] = defaultdict(list)
    for a in answers:
        for stage, ms in a.timings_ms.items():
            stages[stage].append(ms)
    return {
        stage: {"p50": metrics.percentile(v, 50), "p95": metrics.percentile(v, 95)}
        for stage, v in stages.items()
    }


def _spread(values: Sequence[float]) -> dict[str, float]:
    return {
        "min": min(values),
        "p50": metrics.percentile(values, 50),
        "max": max(values),
        "n": len(values),
    }
