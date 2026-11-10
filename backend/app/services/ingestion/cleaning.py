"""Text cleaning, applied to every block after extraction.

Embeddings and keyword search both work on exact characters: "ﬁnance" (one ligature character)
doesn't match "finance", "infor-\\nmation" isn't the word "information", and a zero-width space
splits a word in two. Cleaning removes that noise without changing what the text says.
"""

from __future__ import annotations

import re
import unicodedata

# Typographic ligatures, common in PDFs produced by DTP tools.
_LIGATURES = str.maketrans(
    {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
)
# Space-like characters that should be a plain space (no-break, figure, thin, narrow no-break,
# ideographic, ...).
_SPACES = re.compile(r"[   -   　\t\f\v]")
# Invisible characters to delete: zero-width space/joiners, word joiner, BOM, soft hyphen.
_INVISIBLE = re.compile(r"[​-‍⁠﻿­]")
# Other control characters (newline is kept).
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
# A word broken across lines by a hyphen: "infor-\nmation" -> "information". Only when the next
# line continues in lower case, so "COVID-\n19" and list items are left alone. (Known trade-off:
# a real hyphenated compound split at that point, "well-\nknown", also loses its hyphen.)
_HYPHENATED_BREAK = re.compile(r"(?<=[a-z])-\n(?=[a-z])")
_SPACE_RUN = re.compile(r" {2,}")
_BLANK_LINES = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # NFC, not NFKC: NFKC would also rewrite meaningful characters ("½" -> "1⁄2", "²" -> "2").
    text = unicodedata.normalize("NFC", text).translate(_LIGATURES)
    text = _INVISIBLE.sub("", text)
    text = _SPACES.sub(" ", text)
    text = _CONTROL.sub("", text)
    text = _HYPHENATED_BREAK.sub("", text)
    lines = (_SPACE_RUN.sub(" ", line).strip() for line in text.split("\n"))
    text = "\n".join(lines)
    return _BLANK_LINES.sub("\n\n", text).strip()


def join_wrapped_lines(text: str) -> str:
    """PDF text arrives as visual lines. Within one PDF text block they are one paragraph, so
    join them with spaces (after fixing hyphenated breaks)."""
    text = _HYPHENATED_BREAK.sub("", text.replace("\r\n", "\n"))
    return " ".join(part.strip() for part in text.split("\n") if part.strip())
