"""PDF, DOCX, TXT and Markdown -> Extraction (a list of Blocks + page count + metadata).

Documents are parsed, never executed: PyMuPDF doesn't run PDF JavaScript, and .docx can't hold
macros (we reject archives that carry them anyway). Every failure becomes an ExtractionError
with a message for the user; the library's own message goes to the log only.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from pathlib import Path
from typing import Any

import charset_normalizer
import pymupdf
import yaml
from docx import Document as open_docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.services.ingestion.base import Block, Extraction, ExtractionError
from app.services.ingestion.cleaning import clean_text, join_wrapped_lines

logger = logging.getLogger("app.ingestion")

MAX_PDF_PAGES = 1000
NO_TEXT = (
    "No text could be found in this file. If it's a scanned document (pictures of pages), it "
    "would need OCR, which isn't supported."
)


def extract(path: Path, file_type: str) -> Extraction:
    """Extract and clean a stored upload. Raises ExtractionError for problems with the file."""
    extractor = {"pdf": _pdf, "docx": _docx, "txt": _txt, "md": _markdown}[file_type]
    raw = extractor(path)
    blocks = [
        Block(text, b.page, tuple(clean_text(h) for h in b.headings))
        for b in raw.blocks
        if (text := clean_text(b.text))
    ]
    if not blocks:
        raise ExtractionError(NO_TEXT)
    return Extraction(blocks, raw.page_count, raw.metadata)


# --- PDF -------------------------------------------------------------------------------------


def _pdf(path: Path) -> Extraction:
    try:
        document = pymupdf.open(path, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 - PyMuPDF raises several types for damaged files
        logger.info("PDF could not be opened: %s", type(exc).__name__)
        raise ExtractionError("This PDF is damaged and can't be read.") from None
    with document:
        if document.needs_pass:
            raise ExtractionError(
                "This PDF is password-protected. Remove the password and upload it again."
            )
        if document.page_count == 0:
            raise ExtractionError("This PDF is damaged and can't be read.")
        if document.page_count > MAX_PDF_PAGES:
            raise ExtractionError(f"This PDF has more than {MAX_PDF_PAGES} pages.")
        blocks = []
        for number, page in enumerate(document, start=1):
            # "blocks" = PyMuPDF's paragraphs: (x0, y0, x1, y1, text, block_no, block_type).
            # Type 0 is text (1 is an image). Lines inside one block are one paragraph.
            paragraphs = [join_wrapped_lines(b[4]) for b in page.get_text("blocks") if b[6] == 0]
            text = "\n\n".join(p for p in paragraphs if p)
            if text:
                blocks.append(Block(text, page=number))
        return Extraction(blocks, page_count=document.page_count)


# --- DOCX ------------------------------------------------------------------------------------

_HEADING_STYLE = re.compile(r"^Heading (\d)$")


def _docx(path: Path) -> Extraction:
    try:
        document = open_docx(str(path))
    except Exception as exc:  # noqa: BLE001 - zip, XML and package errors all mean "damaged"
        logger.info("DOCX could not be opened: %s", type(exc).__name__)
        raise ExtractionError("This Word document is damaged and can't be read.") from None

    blocks: list[Block] = []
    headings: list[tuple[int, str]] = []  # (level, text), the path to the current section
    lines: list[str] = []

    def flush() -> None:
        if lines:
            blocks.append(Block("\n".join(lines), headings=tuple(t for _, t in headings)))
            lines.clear()

    # Walk the body in document order: paragraphs and tables are interleaved, and
    # document.paragraphs / document.tables would lose that order.
    for element in document.element.body.iterchildren():
        tag = element.tag.rpartition("}")[2]
        if tag == "p":
            paragraph = Paragraph(element, document)
            text = paragraph.text.strip()
            if not text:
                continue
            style = paragraph.style.name if paragraph.style is not None else ""
            if match := _HEADING_STYLE.match(style):
                flush()
                level = int(match.group(1))
                while headings and headings[-1][0] >= level:
                    headings.pop()
                headings.append((level, text))
            else:
                lines.append(text)
        elif tag == "tbl":
            lines.extend(_table_rows(Table(element, document)))
    flush()
    return Extraction(blocks)


def _table_rows(table: Table) -> list[str]:
    rows = []
    for row in table.rows:
        cells: list[str] = []
        for cell in row.cells:
            text = " ".join(cell.text.split())
            # A merged cell is reported once per grid column it spans: keep it once.
            if text and (not cells or cells[-1] != text):
                cells.append(text)
        if cells:
            rows.append(" | ".join(cells))
    return rows


# --- TXT -------------------------------------------------------------------------------------


# Share of non-ASCII characters (ignoring spaces) above which text isn't treated as Western.
# Measured: ordinary German/French prose ~2-5%, an accent-packed test sentence 21%, Russian in
# cp1251 decoded as cp1252 93%. 30% separates them with a wide margin on both sides.
_WESTERN_MAX_NON_ASCII = 0.3


def decode_text(data: bytes) -> str:
    """Decode an uploaded text file.

    1. A byte-order mark says the encoding outright (UTF-8 or UTF-16).
    2. Strict UTF-8: the modern default, and invalid UTF-8 is very unlikely to be accidental.
    3. Windows-1252, the usual legacy encoding for English/Western European files made on
       Windows, if it decodes and at most 30% of its characters are non-ASCII, as in Western text.
    4. Only then statistical detection (charset-normalizer), which non-Latin text needs.

    Why not detection first: measured on short cp1252 samples, charset-normalizer guessed
    cp1257, cp852 and cp1250, turning "naïve" into "naļve". Detection needs more text than a
    short policy note gives it.
    """
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        text = data.decode("cp1252")
    except UnicodeDecodeError:
        text = None
    if text is not None:
        letters = [c for c in text if not c.isspace()]
        non_ascii = sum(1 for c in letters if ord(c) > 127)
        if letters and non_ascii / len(letters) <= _WESTERN_MAX_NON_ASCII:
            return text
    best = charset_normalizer.from_bytes(data).best()
    if best is None:
        raise ExtractionError(
            "Couldn't work out this file's text encoding. Save it as UTF-8 and upload it again."
        )
    return str(best)


def _txt(path: Path) -> Extraction:
    return Extraction([Block(decode_text(path.read_bytes()))])


# --- Markdown --------------------------------------------------------------------------------

_ATX_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def _markdown(path: Path) -> Extraction:
    text = decode_text(path.read_bytes())
    metadata, body = split_front_matter(text)

    blocks: list[Block] = []
    headings: list[tuple[int, str]] = []
    lines: list[str] = []
    in_fence = False

    def flush() -> None:
        if any(line.strip() for line in lines):
            blocks.append(Block("\n".join(lines), headings=tuple(t for _, t in headings)))
        lines.clear()

    for line in body.split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence  # "# comment" inside a code block isn't a heading
        heading = None if in_fence else _ATX_HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, heading.group(2)))
        else:
            lines.append(line)
    flush()
    return Extraction(blocks, metadata=metadata)


# Front matter keys we keep (the corpus specification's set). Anything else is dropped: the
# metadata comes from the uploaded file, so it is untrusted input like the rest of it.
FRONT_MATTER_KEYS = {
    "document_id", "title", "version", "status", "effective_date", "superseded_date",
    "last_reviewed", "next_review_due", "department_owner", "approved_by", "supersedes",
    "superseded_by", "amends", "amended_by", "classification", "related_documents",
}  # fmt: skip
DOCUMENT_STATUSES = {"current", "superseded", "draft", "archived"}
_MAX_VALUE = 300
_MAX_LIST = 100


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """A leading `---` YAML block becomes metadata; the rest is the body."""
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text
    lines = text.replace("\r\n", "\n").split("\n")
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, text  # no closing line: it was a horizontal rule, not front matter
    try:
        # safe_load builds only plain data (dicts, lists, strings, numbers, dates): a document
        # can't make the YAML parser construct Python objects.
        raw = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError:
        raise ExtractionError(
            "The metadata block at the top of this Markdown file (between the --- lines) isn't "
            "valid YAML."
        ) from None
    body = "\n".join(lines[end + 1 :])
    return (clean_front_matter(raw) if isinstance(raw, dict) else {}), body


def clean_front_matter(raw: dict[Any, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in FRONT_MATTER_KEYS:
            continue
        if isinstance(value, list):
            items = [s for v in value[:_MAX_LIST] if (s := _scalar(v)) is not None]
            cleaned[key] = items
        elif value is None or (s := _scalar(value)) is not None:
            cleaned[key] = None if value is None else s
    status = cleaned.get("status")
    if status is not None:
        status = str(status).lower()
        if status in DOCUMENT_STATUSES:
            cleaned["status"] = status
        else:
            del cleaned["status"]
    return cleaned


def _scalar(value: Any) -> str | None:
    """Dates -> ISO text, numbers -> text ("4.0" stays "4.0"), nested structures dropped."""
    if isinstance(value, dt.date | dt.datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, str | int | float):
        return clean_text(str(value))[:_MAX_VALUE]
    return None
