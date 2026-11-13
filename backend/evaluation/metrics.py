"""Retrieval metrics, written by hand (no evaluation library).

Vocabulary
- A question has a set of **relevant units**: the sections the labelled answer comes from,
  e.g. {"NX-HR-002 v3.0 §4.1", "NX-HR-002 v3.0 §6.2"}.
- Search returns a ranked list of chunks. Each chunk **covers** some units: the sections its text
  overlaps. A chunk matches a relevant unit if it covers that section or one of its subsections
  ("§4.1.2" counts for "§4.1"; "§4", the intro of section 4, does not count for "§4.1").

Per question, for a cut-off K (only the top K results count):
- hit@K        1 if any of the top K chunks matches any relevant unit, else 0
- recall@K     share of the relevant units matched by the top K   (did we find *everything*?)
- precision@K  share of the top K slots holding a matching chunk  (how much of it is useful?)
               divided by K even when fewer results came back: empty slots aren't useful either
- RR@K         1 / rank of the first matching chunk, 0 if none in the top K; its mean is MRR
               (rewards putting the right passage *first*, which matters for an LLM context)

Averaged over questions, hit@K is the "hit rate".
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

Covered = frozenset[str]  # the units one retrieved chunk covers


def unit_matches(covered: str, relevant: str) -> bool:
    """A covered section counts for a relevant one if it is that section or inside it."""
    return covered == relevant or covered.startswith(relevant + ".")


def matched_units(chunk: Iterable[str], relevant: Iterable[str]) -> set[str]:
    """The relevant units this chunk counts for."""
    return {r for r in relevant if any(unit_matches(c, r) for c in chunk)}


def first_relevant_rank(results: Sequence[Covered], relevant: set[str], k: int) -> int | None:
    for rank, chunk in enumerate(results[:k], start=1):
        if matched_units(chunk, relevant):
            return rank
    return None


def hit_at_k(results: Sequence[Covered], relevant: set[str], k: int) -> float:
    return 1.0 if first_relevant_rank(results, relevant, k) else 0.0


def recall_at_k(results: Sequence[Covered], relevant: set[str], k: int) -> float:
    if not relevant:
        raise ValueError("recall is undefined for a question with no relevant units")
    found: set[str] = set()
    for chunk in results[:k]:
        found |= matched_units(chunk, relevant)
    return len(found) / len(relevant)


def precision_at_k(results: Sequence[Covered], relevant: set[str], k: int) -> float:
    useful = sum(1 for chunk in results[:k] if matched_units(chunk, relevant))
    return useful / k


def reciprocal_rank(results: Sequence[Covered], relevant: set[str], k: int) -> float:
    rank = first_relevant_rank(results, relevant, k)
    return 1.0 / rank if rank else 0.0


def mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("mean of an empty list")
    return math.fsum(values) / len(values)


def percentile(values: Sequence[float], p: float) -> float:
    """Nearest-rank percentile: the smallest value with at least p % of the values at or below
    it. p=50 is the median (lower middle for an even count), p=95 a tail latency."""
    if not values:
        raise ValueError("percentile of an empty list")
    if not 0 < p <= 100:
        raise ValueError("p must be in (0, 100]")
    ordered = sorted(values)
    return ordered[math.ceil(p / 100 * len(ordered)) - 1]


def best_threshold(positives: Sequence[float], negatives: Sequence[float]) -> tuple[float, float]:
    """The cut-off t that best separates two score lists with the rule "score >= t means
    positive", and the accuracy it reaches. Candidates are the observed scores themselves
    (plus +inf, i.e. "everything negative"); ties prefer the lower threshold."""
    if not positives or not negatives:
        raise ValueError("need scores on both sides")
    total = len(positives) + len(negatives)
    best = (math.inf, len(negatives) / total)
    for t in sorted({*positives, *negatives}):
        correct = sum(s >= t for s in positives) + sum(s < t for s in negatives)
        if correct / total > best[1] or (correct / total == best[1] and t < best[0]):
            best = (t, correct / total)
    return best
