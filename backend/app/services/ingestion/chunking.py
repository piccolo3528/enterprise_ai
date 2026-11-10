"""Splitting extracted text into chunks for embedding and search (M8). Written from scratch.

How it works:
1. `assemble` joins the extracted blocks into ONE text, writing a heading line wherever the
   heading path changes, and remembers which character range came from which page / section.
2. A strategy returns *spans* (start, end character offsets) into that text, never copies.
   Spans are what let every chunk be mapped back to its pages and section.
3. `chunk_document` turns spans into chunk drafts: trimmed text, token count, page span,
   section label, and (heading-aware only) a short context header.

Strategies (CHUNK_STRATEGY):
- fixed      every `size` tokens; simple, but cuts sentences and words in half
- overlap    fixed windows that share `overlap` tokens, so a fact on a boundary survives whole
- recursive  split at paragraphs -> lines -> sentences -> words until pieces fit, then merge
             neighbours back up to `size`, carrying whole trailing pieces as overlap
- heading    never crosses a top-level section; merges small sibling sections (the corpus's
             median section is 49 tokens); oversized sections fall back to recursive
- auto       heading when the document has headings (Markdown, DOCX), otherwise recursive

Sizes are in embedding-model tokens (tokens.py); no stored chunk ever exceeds the model's 510
content tokens.
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from app.services.ingestion.base import Block
from app.services.ingestion.tokens import MAX_CONTENT_TOKENS, TokenCounter

Span = tuple[int, int]
SECTION_MAX = 300  # the chunks.section column
_HEADER_MAX_CHARS = 200


@dataclass(frozen=True)
class Segment:
    start: int
    end: int
    page: int | None
    headings: tuple[str, ...]


@dataclass(frozen=True)
class Assembled:
    text: str
    segments: list[Segment]

    @cached_property
    def _starts(self) -> list[int]:
        return [s.start for s in self.segments]

    def segment_at(self, offset: int) -> Segment:
        """The segment containing this character offset (binary search)."""
        return self.segments[max(0, bisect.bisect_right(self._starts, offset) - 1)]


@dataclass(frozen=True)
class ChunkDraft:
    index: int
    text: str  # what is stored, embedded and keyword-searched (header included, if any)
    token_count: int
    page_start: int | None
    page_end: int | None
    section: str | None
    strategy: str


# --- 1. one text with a map back to pages and sections ----------------------------------------


def assemble(blocks: Iterable[Block]) -> Assembled:
    parts: list[str] = []
    segments: list[Segment] = []
    position = 0
    previous: tuple[str, ...] = ()
    for block in blocks:
        common = 0
        while (
            common < min(len(previous), len(block.headings))
            and previous[common] == block.headings[common]
        ):
            common += 1
        # Write the headings that are new here, so they are part of the searchable text.
        piece = "\n".join([*block.headings[common:], block.text])
        if parts:
            parts.append("\n\n")
            position += 2
        segments.append(Segment(position, position + len(piece), block.page, block.headings))
        parts.append(piece)
        position += len(piece)
        previous = block.headings
    return Assembled("".join(parts), segments)


# --- 2. strategies: text -> spans -------------------------------------------------------------


def token_windows(
    text: str, start: int, end: int, tokens: TokenCounter, size: int, overlap: int = 0
) -> list[Span]:
    """Windows of `size` tokens, each starting `size - overlap` tokens after the previous one."""
    offsets = [(start + a, start + b) for a, b in tokens.offsets(text[start:end])]
    spans: list[Span] = []
    step = size - overlap
    i = 0
    while i < len(offsets):
        window = offsets[i : i + size]
        spans.append((window[0][0], window[-1][1]))
        if i + size >= len(offsets):
            break
        i += step
    return spans


# Coarsest to finest. Each split keeps the separator with the piece before it, so pieces are
# contiguous and joining them gives back the exact original text.
_SEPARATORS = [
    re.compile(r"\n\s*\n"),  # paragraphs
    re.compile(r"\n"),  # lines
    re.compile(r"(?<=[.!?;:])\s+"),  # sentences
    re.compile(r"\s+"),  # words
]


@dataclass(frozen=True)
class _Piece:
    start: int
    end: int
    tokens: int


def recursive_spans(
    text: str, start: int, end: int, tokens: TokenCounter, size: int, overlap: int
) -> list[Span]:
    pieces = _pieces(text, start, end, tokens, size, level=0)
    return _merge(pieces, size, overlap)


def _pieces(
    text: str, start: int, end: int, tokens: TokenCounter, size: int, level: int
) -> list[_Piece]:
    count = tokens.count(text[start:end])
    if count <= size:
        return [_Piece(start, end, count)]
    if level == len(_SEPARATORS):  # a single "word" longer than a chunk: cut by tokens
        return [
            _Piece(a, b, tokens.count(text[a:b]))
            for a, b in token_windows(text, start, end, tokens, size)
        ]
    cuts = [m.end() for m in _SEPARATORS[level].finditer(text, start, end) if m.end() < end]
    bounds = [start, *cuts, end]
    if len(bounds) == 2:  # this separator doesn't occur here: try the next, finer one
        return _pieces(text, start, end, tokens, size, level + 1)
    result: list[_Piece] = []
    for a, b in zip(bounds, bounds[1:], strict=False):
        if a < b:
            result.extend(_pieces(text, a, b, tokens, size, level + 1))
    return result


def _merge(pieces: list[_Piece], size: int, overlap: int) -> list[Span]:
    """Greedily join neighbouring pieces up to `size` tokens. A new chunk starts with the
    previous chunk's last whole pieces, up to `overlap` tokens (so overlap never cuts a
    sentence; a sentence longer than `overlap` simply isn't repeated)."""
    spans: list[Span] = []
    current: list[_Piece] = []
    total = 0
    for piece in pieces:
        if current and total + piece.tokens > size:
            spans.append((current[0].start, current[-1].end))
            carried: list[_Piece] = []
            carried_tokens = 0
            for previous in reversed(current):
                if carried_tokens + previous.tokens > overlap:
                    break
                carried.insert(0, previous)
                carried_tokens += previous.tokens
            while carried and carried_tokens + piece.tokens > size:
                carried_tokens -= carried.pop(0).tokens
            current, total = carried, carried_tokens
        current.append(piece)
        total += piece.tokens
    if current:
        spans.append((current[0].start, current[-1].end))
    return spans


def heading_spans(
    assembled: Assembled, tokens: TokenCounter, size: int, overlap: int
) -> list[Span]:
    """Chunks stay inside one top-level section. Within it, whole subsections are merged up to
    `size`; a subsection that is too big on its own is split recursively."""
    text = assembled.text
    spans: list[Span] = []
    for group in _top_level_groups(assembled):
        current: list[_Piece] = []
        total = 0
        for leaf in _leaves(group):
            n = tokens.count(text[leaf.start : leaf.end])
            if n > size:
                if current:
                    spans.append((current[0].start, current[-1].end))
                    current, total = [], 0
                spans.extend(recursive_spans(text, leaf.start, leaf.end, tokens, size, overlap))
                continue
            if current and total + n > size:
                spans.append((current[0].start, current[-1].end))
                current, total = [], 0
            current.append(_Piece(leaf.start, leaf.end, n))
            total += n
        if current:
            spans.append((current[0].start, current[-1].end))
    return spans


def _document_title(assembled: Assembled) -> str | None:
    """A single first-level heading shared by every headed block is the document's title."""
    firsts = {s.headings[0] for s in assembled.segments if s.headings}
    return firsts.pop() if len(firsts) == 1 else None


def _top_level_groups(assembled: Assembled) -> list[list[Segment]]:
    depth = 2 if _document_title(assembled) else 1
    groups: list[list[Segment]] = []
    key: tuple[str, ...] | None = None
    for segment in assembled.segments:
        segment_key = segment.headings[:depth]
        if not groups or segment_key != key:
            groups.append([])
            key = segment_key
        groups[-1].append(segment)
    return groups


def _leaves(group: list[Segment]) -> list[Segment]:
    """Consecutive segments under the same full heading path form one subsection."""
    leaves: list[Segment] = []
    for segment in group:
        if leaves and leaves[-1].headings == segment.headings:
            last = leaves[-1]
            leaves[-1] = Segment(last.start, segment.end, last.page, last.headings)
        else:
            leaves.append(segment)
    return leaves


# --- 3. spans -> chunk drafts ---------------------------------------------------------------


def chunk_document(
    blocks: list[Block],
    metadata: dict[str, Any],
    tokens: TokenCounter,
    *,
    strategy: str = "auto",
    size: int = 400,
    overlap: int = 60,
) -> list[ChunkDraft]:
    assembled = assemble(blocks)
    text = assembled.text
    if strategy == "auto":
        strategy = "heading" if any(b.headings for b in blocks) else "recursive"

    if strategy == "fixed":
        spans = token_windows(text, 0, len(text), tokens, size)
    elif strategy == "overlap":
        spans = token_windows(text, 0, len(text), tokens, size, overlap)
    elif strategy == "recursive":
        spans = recursive_spans(text, 0, len(text), tokens, size, overlap)
    elif strategy == "heading":
        spans = heading_spans(assembled, tokens, size, overlap)
    else:
        raise ValueError(f"unknown chunking strategy {strategy!r}")

    title = _document_title(assembled)
    label = _document_label(metadata)
    drafts: list[ChunkDraft] = []
    for start, end in _enforce_limit(text, (_trim(text, s, e) for s, e in spans), tokens):
        if start >= end:
            continue
        section = _section(assembled, start, end, title)
        body = text[start:end]
        if strategy == "heading" and (label or section):
            header = " · ".join(p for p in (label, section) if p)[:_HEADER_MAX_CHARS]
            stored = f"{header}\n\n{body}"
            if tokens.count(stored) > MAX_CONTENT_TOKENS:
                stored = body  # never let the header push a chunk past the model's limit
        else:
            stored = body
        drafts.append(
            ChunkDraft(
                index=len(drafts),
                text=stored,
                token_count=tokens.count(stored),
                page_start=assembled.segment_at(start).page,
                page_end=assembled.segment_at(end - 1).page,
                section=section,
                strategy=strategy,
            )
        )
    return drafts


def _trim(text: str, start: int, end: int) -> Span:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _enforce_limit(text: str, spans: Iterable[Span], tokens: TokenCounter) -> list[Span]:
    """Safety net: re-tokenising a slice can differ slightly from counting it in context, so any
    span over the model's hard limit is cut into token windows."""
    result: list[Span] = []
    for start, end in spans:
        if tokens.count(text[start:end]) <= MAX_CONTENT_TOKENS:
            result.append((start, end))
        else:
            windows = token_windows(text, start, end, tokens, MAX_CONTENT_TOKENS - 10)
            result.extend(_trim(text, a, b) for a, b in windows)
    return result


def _document_label(metadata: dict[str, Any]) -> str | None:
    document_id = metadata.get("document_id")
    if not document_id:
        return None
    version = metadata.get("version")
    return f"{document_id} v{version}" if version else str(document_id)


def _section(assembled: Assembled, start: int, end: int, title: str | None) -> str | None:
    first = _path(assembled.segment_at(start).headings, title)
    last = _path(assembled.segment_at(end - 1).headings, title)
    if not first:
        return last[-1][:SECTION_MAX] if last else None
    label = " › ".join(first)
    if last and last != first:
        label += f" – {last[-1]}"  # a chunk that merged several subsections
    return label[:SECTION_MAX]


def _path(headings: tuple[str, ...], title: str | None) -> tuple[str, ...]:
    return headings[1:] if title and headings and headings[0] == title else headings
