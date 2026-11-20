"""Version-aware retrieval (S4, the corpus spec's retrieval rules 1–3; M14).

Policies change: the leave policy has a current v3.0 (20 days) and a superseded v2.0 (18 days),
and both are in the knowledge base on purpose. Similarity search can't tell which one is in force,
and M11 measured an old version ranked above the current one for 2 of 15 such questions (hybrid).

Rules, from each document's front matter (`status`, `effective_date`, `superseded_date`, `amends`):
1. **Current versions first.** A passage from a superseded/archived/draft document is moved
   below every current one ("demote"), or removed ("filter").
2. **Unless the question needs it:** it asks about the past ("previous", "old policy", "what did
   v2.0 say") or mentions a date inside that version's validity window ("on 31 December 2025"),
   because a superseded version still governs what happened while it was in force (GOV-001 §7.4).
3. **Amendments travel with their base document** (`amendment_codes`): when a passage of a
   document is retrieved, the documents that amend it are fetched too (rag.py does the search).

Documents without front matter (most uploads) have no `status`: they count as current, so these
rules only ever act on documents that say they are outdated.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Literal

from app.services.retrieval import SearchResult

VersionMode = Literal["off", "demote", "filter"]

_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))

_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
_DAY_MONTH_YEAR = re.compile(rf"\b{_DAY}\s+({_MONTH})\.?,?\s+(\d{{4}})\b", re.I)
_MONTH_DAY_YEAR = re.compile(rf"\b({_MONTH})\.?\s+{_DAY},?\s+(\d{{4}})\b", re.I)
_MONTH_YEAR = re.compile(rf"\b({_MONTH})\.?,?\s+(\d{{4}})\b", re.I)
_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")

# Words that ask about an earlier rule. "v2.0" / "version 2" ask about a specific version.
_HISTORICAL = re.compile(
    r"\b(previous(?:ly)?|prior|former(?:ly)?|old(?:er)?\s+(?:polic(?:y|ies)|rules?|versions?)|"
    r"earlier\s+versions?|used\s+to|no\s+longer|superseded|archived|outdated|"
    r"before\s+the\s+(?:new|current|change|update)|v\d+(?:\.\d+)?|version\s+\d+(?:\.\d+)?)\b",
    re.I,
)

Interval = tuple[date, date]


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def mentioned_dates(text: str) -> list[Interval]:
    """Dates and periods a question mentions, as inclusive intervals: "31 December 2025" is one
    day, "November 2025" a month, a bare "2025" the whole year."""
    intervals: list[Interval] = []
    spans: list[tuple[int, int]] = []

    def taken(m: re.Match[str]) -> bool:
        return any(m.start() < end and start < m.end() for start, end in spans)

    def add(m: re.Match[str], interval: Interval | None) -> None:
        if interval and not taken(m):
            intervals.append(interval)
            spans.append(m.span())

    for m in _ISO_DATE.finditer(text):
        d = _safe_date(int(m[1]), int(m[2]), int(m[3]))
        add(m, (d, d) if d else None)
    for m in _DAY_MONTH_YEAR.finditer(text):
        d = _safe_date(int(m[3]), _MONTHS[m[2].lower()], int(m[1]))
        add(m, (d, d) if d else None)
    for m in _MONTH_DAY_YEAR.finditer(text):
        d = _safe_date(int(m[3]), _MONTHS[m[1].lower()], int(m[2]))
        add(m, (d, d) if d else None)
    for m in _MONTH_YEAR.finditer(text):
        year, month = int(m[2]), _MONTHS[m[1].lower()]
        last = calendar.monthrange(year, month)[1]
        add(m, (date(year, month, 1), date(year, month, last)))
    for m in _YEAR.finditer(text):
        year = int(m[1])
        add(m, (date(year, 1, 1), date(year, 12, 31)))
    return intervals


def is_historical(text: str) -> bool:
    return bool(_HISTORICAL.search(text))


def _iso(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def is_current(metadata: dict | None) -> bool:
    status = (metadata or {}).get("status")
    return status is None or str(status).lower() == "current"


def in_force_during(metadata: dict | None, intervals: Iterable[Interval]) -> bool:
    """Was this version in force at any point of these intervals? Needs its effective date;
    an open end (no superseded date) means "still in force"."""
    meta = metadata or {}
    start = _iso(meta.get("effective_date"))
    if start is None:
        return False
    end = _iso(meta.get("superseded_date")) or date.max
    return any(a <= end and start <= b for a, b in intervals)


def prefer_current(
    results: Sequence[SearchResult], query: str, *, mode: VersionMode
) -> list[SearchResult]:
    """Rule 1 and 2: outdated passages go below current ones (demote) or away (filter), unless
    the question asks about the past or names a date when that version was in force. The order
    within each group is kept."""
    if mode == "off" or is_historical(query):
        return list(results)
    dates = mentioned_dates(query)
    keep, outdated = [], []
    for r in results:
        meta = r.passage.doc_metadata
        if is_current(meta) or (dates and in_force_during(meta, dates)):
            keep.append(r)
        else:
            outdated.append(r)
    return keep if mode == "filter" else keep + outdated


def amendments_to_fetch(
    results: Sequence[SearchResult], amendments: Iterable[tuple[object, dict]]
) -> list[object]:
    """Rule 3: the amendments (document ids) whose base document is among the results.
    `amendments` is (document id, front matter) for every ready document of the knowledge base
    that names a base in `amends` ("NX-FIN-001 v2.0"). The amendment's own front matter is the
    authority: a base document isn't always updated to list its amendments. Outdated amendments
    are skipped, like any outdated document."""
    present = {
        f"{m.get('document_id')} v{m.get('version')}"
        for r in results
        if (m := r.passage.doc_metadata or {}).get("document_id")
    }
    return [
        document_id
        for document_id, meta in amendments
        if str(meta.get("amends") or "").strip() in present and is_current(meta)
    ]
