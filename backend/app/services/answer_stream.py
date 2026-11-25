"""Turning the model's raw text stream into what the reader may see, as it arrives (M13, D68).

Two things are only certain once the whole answer exists, yet the reader should see text at once:

1. **"Not found"** (D62). The model replies exactly `NOT_FOUND` when the sources don't answer.
   `NotFoundGate` holds the first characters back while they could still be that reply
   ("N", "NOT_", "**NOT"...) and releases them as soon as they can't be. `TrailingNotFound`
   does the same for the marker at the *end* of an explanation (M16): the explanation is shown,
   and the answer counts as "not found".
2. **Citations** (§4.6). Numbers that weren't given are removed and the rest renumbered in order
   of first use. `CitationStream` applies the same `CitationResolver` piece by piece, holding back
   only text that could still become part of a citation: an unclosed `[2, ` or a `[6.1]` whose
   next character decides whether it's a Markdown link, plus trailing whitespace (a removed
   citation takes the space before it along).

Both are exact: the text streamed, joined, equals what `is_not_found` / `resolve_citations` give
for the complete answer (tested on every split point), so the reader never sees a number change.
"""

from __future__ import annotations

import re

from app.services.citations import CitationResolver
from app.services.llm.prompts import NOT_FOUND, TRAILING_NOT_FOUND, is_not_found

# From a "[" to the end: digits, separators and spaces only (still possibly a citation or section
# reference), optionally closed by "]" as the very last character (the next one may be "(").
_OPEN_BRACKET = re.compile(r"\[[\s\d.,\-–]*\]?")
_TRAILING_SPACE = re.compile(r"\s*\Z")
# An end of text that could still grow into TRAILING_NOT_FOUND: decoration/space, then a prefix
# of the marker ("N" ... "NOT_FOUN"), or the whole marker with its closing decoration.
_MAYBE_TRAILING = re.compile(
    r"[\s*_`'\"]*(?<![A-Za-z0-9])"
    r"(?:NOT_FOUND[\s*_`'\".!]*|N(?:O(?:T(?:_(?:F(?:O(?:U(?:N)?)?)?)?)?)?)?)?\Z"
)


class NotFoundGate:
    """Holds the start of the answer until it is clearly not the NOT_FOUND reply."""

    def __init__(self) -> None:
        self.state = "undecided"  # then "answer" or "not_found"
        self._held = ""

    def _release(self) -> str:
        self.state = "answer"
        released, self._held = self._held.lstrip(), ""
        return released

    def feed(self, text: str) -> str:
        """The text that may be shown now ("" while undecided or not found)."""
        if self.state == "answer":
            return text
        if self.state == "not_found":
            return ""
        self._held += text
        # The same normalisation as is_not_found(): decoration such as **NOT_FOUND** counts.
        head = self._held.strip().lstrip("*_`'\" ").upper()
        if head.startswith(NOT_FOUND):
            self.state, self._held = "not_found", ""
            return ""
        if not head or NOT_FOUND.startswith(head):
            return ""  # "N", "NOT_FO", "**": could still be the not-found reply
        return self._release()

    def finish(self) -> str:
        """End of the stream: whatever was still held, if it turned out to be an answer."""
        if self.state != "undecided":
            return ""
        if is_not_found(self._held):
            self.state, self._held = "not_found", ""
            return ""
        return self._release()


class TrailingNotFound:
    """Holds back the end of the answer while it could still be a trailing NOT_FOUND (M16).

    The model sometimes explains what the sources lack and then signs off with the marker (Q044).
    The explanation streams normally; only a tail such as " N", " NOT_FO" or " **NOT_FOUND**" is
    held, and dropped at the end if it completes the marker. "NOT_FOUND items" mid-answer is
    released as soon as the next word arrives. The result equals `split_trailing_not_found` on
    the whole answer.
    """

    def __init__(self) -> None:
        self.found = False
        self._held = ""
        self._released = False  # any non-blank text released: an explanation exists
        # The last character released: the marker must be its own word, and "X" released in an
        # earlier piece still decides whether "NOT_FOUND" is glued to it. Searching from
        # pos=len(context) lets the regex's look-behind see that character.
        self._context = ""

    def feed(self, text: str) -> str:
        buffer = self._context + self._held + text
        match = _MAYBE_TRAILING.search(buffer, len(self._context))
        cut = match.start() if match else len(buffer)
        released = buffer[len(self._context) : cut]
        self._held = buffer[cut:]
        if released:
            self._context = released[-1]
            self._released = self._released or bool(released.strip())
        return released

    def finish(self) -> str:
        held, self._held = self._held, ""
        if self._released and TRAILING_NOT_FOUND.match(self._context + held, len(self._context)):
            self.found = True
            return ""
        return held


class CitationStream:
    """Validates and renumbers citations as the answer streams (see the module docstring)."""

    def __init__(self, source_count: int) -> None:
        self.resolver = CitationResolver(source_count)
        self._pending = ""

    @staticmethod
    def _safe_end(text: str) -> int:
        """How much of `text` can be resolved now: up to any bracket that may still become a
        citation, and before trailing whitespace."""
        end = _TRAILING_SPACE.search(text).start()
        bracket = text.rfind("[")
        if bracket != -1 and _OPEN_BRACKET.fullmatch(text, bracket):
            end = min(end, _TRAILING_SPACE.search(text, 0, bracket).start())
        return end

    def feed(self, text: str) -> str:
        self._pending += text
        end = self._safe_end(self._pending)
        ready, self._pending = self._pending[:end], self._pending[end:]
        return self.resolver.apply(ready) if ready else ""

    def finish(self) -> str:
        ready, self._pending = self._pending.rstrip(), ""
        return self.resolver.apply(ready) if ready else ""
