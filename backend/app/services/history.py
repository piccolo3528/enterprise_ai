"""Which earlier messages a follow-up question gets to see (M13, ARCHITECTURE §4.5).

The rewriter needs the recent conversation to resolve "they" or "that policy", but not all of it:
every token costs time and free-tier quota, and old turns rarely matter. So:

- at most HISTORY_MAX_TURNS question/answer pairs are loaded (the query's LIMIT);
- earlier answers lose their [n] markers (they point at sources the rewriter never sees);
- messages are taken newest first while they fit HISTORY_TOKEN_BUDGET, then put back in order:
  the oldest are dropped first;
- if even the newest message is over the budget, its beginning is kept (answers lead with the
  direct answer, prompt rule 6), so a follow-up always sees the turn it most likely refers to.

Tokens are counted with the embedding tokenizer, an approximation of Gemini's count (L54).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.services.ingestion.tokens import TokenCounter
from app.services.llm.prompts import strip_citations

History = list[tuple[str, str]]  # (role, text), oldest first; role "user" or "assistant"


def _cut_to_tokens(text: str, budget: int, tokens: TokenCounter) -> str:
    offsets = tokens.offsets(text)
    if len(offsets) <= budget:
        return text
    return text[: offsets[budget - 1][1]].rstrip() + " …"


def select_history(messages: Sequence[tuple[str, str]], *, budget: int,
                   tokens: TokenCounter) -> History:  # fmt: skip
    """The newest messages that fit `budget` tokens, oldest first (see the module docstring)."""
    chosen: History = []
    used = 0
    for role, text in reversed(messages):
        if role == "assistant":
            text = strip_citations(text)
        size = tokens.count(text)
        if used + size <= budget:
            chosen.append((role, text))
            used += size
            continue
        if not chosen:
            chosen.append((role, _cut_to_tokens(text, budget, tokens)))
        break
    chosen.reverse()
    return chosen
