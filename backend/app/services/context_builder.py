"""Context builder v1: which retrieved passages the LLM sees, in what order, labelled how (§4.5).

v1 rules:
- **Rank order.** Passages arrive best-first from hybrid retrieval and keep that order, so the
  most relevant text is first. (Reordering against "lost in the middle", merging adjacent chunks
  and compression are measured in M14.)
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
from collections.abc import Sequence
from dataclasses import dataclass

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
    """"NX-HR-002 v3.0 · Annual Leave Policy" from front matter, else the file name."""
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


def build_context(
    results: Sequence[SearchResult], *, max_sources: int, token_budget: int
) -> Context:
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
        sources.append(
            Source(len(sources) + 1, result, looks_like_injection(result.passage.text))
        )
    return Context(sources, used, skipped)
