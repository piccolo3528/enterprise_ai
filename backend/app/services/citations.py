"""Checking the model's citations against the sources it was actually given (§4.6, layer 4).

The model writes `[2]`, `[2][5]`, `[2, 5]` or `[2-4]`. After the answer is complete:
- a number that isn't one of the sources (a model can invent `[7]` when given 5 sources) is
  **removed** and counted, so the reader never sees a citation that leads nowhere;
- the remaining sources are **renumbered 1..m in order of first use**, so the answer reads [1],
  [2], [3] and the citation panel lists exactly the cited passages in that order;
- repeats inside one bracket (`[2, 2]`) collapse.

- a bracketed **section number** (`[6.1]`) or list of them (`[5.1, 6.1]`) is rewritten as `(§6.1)`
  / `(§5.1, §6.1)`: measured on the 57 evaluation questions, one answer per run wrote section
  numbers in brackets (once as a list), which readers take for citations.

Only bracketed digits are touched: Markdown links `[text](url)` and other brackets are left alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NUMBER = r"\d{1,3}(?:\s*[-–]\s*\d{1,3})?"
# Optional whitespace before the bracket is captured, so a removed citation doesn't leave a
# double space ("10 days [9]." -> "10 days.").
_CITATION = re.compile(rf"(\s*)\[\s*({_NUMBER}(?:\s*,\s*{_NUMBER})*)\s*\]")
_MAX_RANGE = 20  # "[1-999]" isn't a citation anyone means
_SECTION = r"\d{1,3}(?:\.\d{1,3})+"  # 6.1, 4.2.3
_ITEM = rf"(?:{_SECTION}|{_NUMBER})"
# A bracket of source and/or section numbers, not a Markdown link. Only brackets containing a
# section number are changed: "[2, 6.1]" -> "(§6.1)[2]", whose [2] the citation rules then handle.
_SECTION_REF = re.compile(rf"\[\s*({_ITEM}(?:\s*,\s*{_ITEM})*)\s*\](?!\()")


@dataclass(frozen=True)
class ResolvedCitations:
    text: str  # the answer with valid, renumbered citations
    order: list[int]  # original source numbers, in the order of the new numbers 1..m
    invalid: int  # citation numbers dropped because no such source was given


def _expand(token: str) -> list[int]:
    parts = re.split(r"\s*[-–]\s*", token.strip())
    if len(parts) == 1:
        return [int(parts[0])]
    low, high = int(parts[0]), int(parts[1])
    if low > high or high - low >= _MAX_RANGE:
        return [low, high]  # not a sensible range: judge the two ends on their own
    return list(range(low, high + 1))


class CitationResolver:
    """The rules above, applied to an answer in one go or piece by piece (streaming): the
    renumbering is shared across pieces, so [7] stays [1] wherever it appears later."""

    def __init__(self, source_count: int) -> None:
        self.source_count = source_count
        self.new_number: dict[int, int] = {}  # original source number -> new number
        self.invalid = 0

    @property
    def order(self) -> list[int]:
        return list(self.new_number)

    def _replace(self, match: re.Match[str]) -> str:
        markers: list[str] = []
        for token in match.group(2).split(","):
            for n in _expand(token):
                if 1 <= n <= self.source_count:
                    new = self.new_number.setdefault(n, len(self.new_number) + 1)
                    if f"[{new}]" not in markers:
                        markers.append(f"[{new}]")
                else:
                    self.invalid += 1
        if not markers:
            return ""
        return match.group(1) + "".join(markers)

    @staticmethod
    def _section_ref(match: re.Match[str]) -> str:
        items = [item.strip() for item in match.group(1).split(",")]
        sections = [item for item in items if "." in item]
        if not sections:
            return match.group(0)  # a plain citation
        numbers = [item for item in items if "." not in item]
        return (
            "("
            + ", ".join(f"§{s}" for s in sections)
            + ")"
            + (f"[{', '.join(numbers)}]" if numbers else "")
        )

    def apply(self, text: str) -> str:
        return _CITATION.sub(self._replace, _SECTION_REF.sub(self._section_ref, text))


def resolve_citations(answer: str, source_count: int) -> ResolvedCitations:
    resolver = CitationResolver(source_count)
    text = resolver.apply(answer)
    return ResolvedCitations(text=text, order=resolver.order, invalid=resolver.invalid)
