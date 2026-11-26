"""Context builder v1: which retrieved passages the LLM sees, in what order, labelled how (§4.5).

v1 rules:
- **Rank order.** Passages arrive best-first from retrieval and keep that order, so the most
  relevant text is first. Two alternatives exist to be measured on answers (M15, D76):
  `order="sandwich"` (best first, second-best last, against "lost in the middle") and
  `compress_terms` (keep only the sentences sharing a word with the question, plus neighbours).
- **At most CONTEXT_MAX_SOURCES passages** (10: M11's hybrid Hit@10 is 100 %).
- **A token budget** (CONTEXT_TOKEN_BUDGET, 5000). A passage that doesn't fit is skipped and the
  next, smaller one may still fit. Counted with the embedding model's tokenizer (stored per
  chunk), which differs from Gemini's: the budget is a guide, not an exact limit (L54).
- **Labels from front matter.** Code, version, title and status come from the document's
  metadata, so the model can prefer the current version (M11: an archived version ranked first
  for 6 of 15 multi-version questions in semantic mode, 2 in hybrid).
- **Injection flagging.** A passage that looks like it addresses the model ("ignore previous
  instructions", a fake `</source>` tag, ...) is flagged and logged by chunk id. It is *not*
  removed: patterns produce false positives, and the prompt + escaping already defend against it;
  the flag tells the reader to look at that citation critically.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from app.services.llm.prompts import SourceInput
from app.services.retrieval import SearchResult

# Phrases aimed at an AI rather than at an employee. Checked against the 22-policy evaluation
# corpus: none of its passages match (tests/unit/test_answering.py).
_INJECTION_PATTERNS = [
    r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|"
    r"preceding|all|any|system|these|your)\b[^.\n]{0,25}\b(instructions?|rules?|prompts?|"
    r"directions?|guidelines)\b",
    r"\byou are (now|no longer)\b",
    r"\b(reveal|print|show|repeat|output|disclose)\b[^.\n]{0,30}\b(system prompt|your "
    r"(instructions|prompt|rules))\b",
    r"\bsystem prompt\b",
    r"\bnew instructions?\s*:",
    r"<\s*/?\s*(source|sources|question|system|instructions?)\b",
    r"\b(act|pretend|behave)\s+(as|like|to be)\b[^.\n]{0,40}\b(ai|assistant|model|chatbot|llm)\b",
    r"\b(as an ai|language model)\b[^.\n]{0,40}\b(you must|you should|always|never)\b",
]
_INJECTION = re.compile("|".join(f"(?:{p})" for p in _INJECTION_PATTERNS), re.IGNORECASE)


def looks_like_injection(text: str) -> bool:
    """Best-effort heuristic. A match means "worth a look", not "malicious"; no match proves
    nothing (an attacker can rephrase)."""
    return _INJECTION.search(text) is not None


def document_label(filename: str, metadata: dict | None) -> str:
    """ "NX-HR-002 v3.0 · Annual Leave Policy" from front matter, else the file name."""
    meta = metadata or {}
    code, version, title = meta.get("document_id"), meta.get("version"), meta.get("title")
    if not code and not title:
        return filename
    head = " ".join(str(part) for part in (code, f"v{version}" if version else None) if part)
    return " · ".join(part for part in (head, str(title) if title else None) if part)


def _pages(start: int | None, end: int | None) -> str | None:
    if start is None:
        return None
    return str(start) if end in (None, start) else f"{start}-{end}"


@dataclass(frozen=True)
class Source:
    number: int  # 1-based, as cited in the answer: [1], [2], ...
    result: SearchResult
    flagged: bool

    def prompt_input(self) -> SourceInput:
        p = self.result.passage
        status = (p.doc_metadata or {}).get("status")
        return SourceInput(
            number=self.number,
            document=document_label(p.filename, p.doc_metadata),
            text=p.text,
            status=str(status) if status else None,
            section=p.section,
            pages=_pages(p.page_start, p.page_end),
        )


@dataclass(frozen=True)
class Context:
    sources: list[Source]
    tokens: int  # embedding-model tokens of the passages included
    skipped: int  # passages left out because they didn't fit the budget


Order = Literal["rank", "sandwich"]

_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an and any are as at be by can could do does for from get has have how i if in is it its "
    "many may me much my of on "
    "or our should so that the their there they this to was we what when where which who why "
    "will with would you your".split()
)
_SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+(?=[A-Z0-9(])")


def query_terms(texts: Iterable[str]) -> set[str]:
    """Content words of the question (and its phrasings), cut to 5 letters as a crude stem, so
    "carried" matches "carry", "reimbursement" matches "reimbursed"."""
    return {w[:5] for t in texts for w in _WORD.findall(t.lower()) if w not in _STOP and len(w) > 2}


def compress_passage(text: str, terms: set[str], *, neighbours: int = 1) -> str:
    """Keep the passage's first line (the context header: document › section), the units that
    share a term with the question, and `neighbours` units on each side; "…" marks a gap. Units
    are lines, and sentences within a line. Nothing matches → the passage is returned whole: an
    empty source would be worse than a long one."""
    lines = text.split("\n")
    head, body = lines[0], lines[1:]
    units = [u for line in body for u in (_SENTENCE_END.split(line) if line.strip() else [line])]
    hits = [i for i, u in enumerate(units)
            if {w[:5] for w in _WORD.findall(u.lower())} & terms]  # fmt: skip
    if not hits:
        return text
    keep = {
        j for i in hits for j in range(i - neighbours, i + neighbours + 1) if 0 <= j < len(units)
    }
    out, gap = [head], False
    for i, unit in enumerate(units):
        if i in keep:
            out.append(unit)
            gap = False
        elif not gap and unit.strip():
            out.append("…")
            gap = True
    return "\n".join(out)


def _sandwich(items: list[SearchResult]) -> list[SearchResult]:
    """1st, 3rd, 5th … then … 6th, 4th, 2nd: the two best passages at the two ends."""
    return items[0::2] + items[1::2][::-1]


def build_context(
    results: Sequence[SearchResult],
    *,
    max_sources: int,
    token_budget: int,
    order: Order = "rank",
    compress_terms: set[str] | None = None,
    tokens=None,
) -> Context:
    """`compress_terms` + `tokens` (a TokenCounter): compressed passages are re-counted, so the
    budget sees their real size."""
    if compress_terms:
        compressed = []
        for r in results:
            text = compress_passage(r.passage.text, compress_terms)
            if text != r.passage.text:
                count = tokens.count(text) if tokens else r.passage.token_count
                r = replace(r, passage=replace(r.passage, text=text, token_count=count))
            compressed.append(r)
        results = compressed
    sources: list[Source] = []
    used = skipped = 0
    for result in results:
        if len(sources) == max_sources:
            break
        cost = result.passage.token_count
        if used + cost > token_budget:
            skipped += 1
            continue
        used += cost
        sources.append(Source(len(sources) + 1, result, looks_like_injection(result.passage.text)))
    if order == "sandwich" and len(sources) > 2:
        reordered = _sandwich([s.result for s in sources])
        by_id = {s.result.passage.chunk_id: s for s in sources}
        sources = [replace(by_id[r.passage.chunk_id], number=i)
                   for i, r in enumerate(reordered, start=1)]  # fmt: skip
    return Context(sources, used, skipped)
