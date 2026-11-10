"""The representation every extractor produces, whatever the file type."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Block:
    """A run of text from one place in the document.

    `page` is 1-based and set only for PDFs (DOCX, TXT and Markdown have no pages).
    `headings` is the path of headings above the text, e.g. ("4. Leave Types", "4.2 Annual leave"):
    that is what lets a chunk (M8) and a citation (M12) say *where* the text came from.
    """

    text: str
    page: int | None = None
    headings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Extraction:
    blocks: list[Block]
    page_count: int | None = None  # PDFs only
    metadata: dict[str, Any] = field(default_factory=dict)  # Markdown front matter (S2)

    @property
    def characters(self) -> int:
        return sum(len(b.text) for b in self.blocks)


class ExtractionError(Exception):
    """A problem with the file itself. `message` is safe to show the user and is stored as the
    document's `error_message`; library error text (which can contain paths) never is."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
