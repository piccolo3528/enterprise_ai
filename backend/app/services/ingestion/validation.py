"""Checks that run inside the upload request, before it is accepted (ARCHITECTURE §4.9).

The browser's filename and Content-Type are claims, not facts. A file is accepted only when its
extension is on the allow-list AND its first bytes match that type. Deeper problems (encrypted,
damaged, no text) are found by the background extraction and reported as `failed`.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path, PureWindowsPath

from app.core.errors import InvalidFileError, UnsupportedFileError

ALLOWED_TYPES = {"pdf": "PDF", "docx": "Word", "txt": "text", "md": "Markdown"}
ALLOWED_MESSAGE = "Only PDF, Word (.docx), Markdown (.md) and text (.txt) files can be uploaded."

# DOCX is a ZIP archive. A "zip bomb" is a small archive that unpacks to gigabytes; python-docx
# would try to read it into memory. The declared sizes inside the archive are checked first.
DOCX_MAX_UNCOMPRESSED = 200 * 1024 * 1024
DOCX_MAX_ENTRIES = 5_000

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
FILENAME_MAX = 255


def display_filename(raw: str | None) -> str:
    """The user's filename, kept only as text to display (never used as a path).

    Browsers usually send just the name, but a client can send "..\\..\\x.pdf" or a full Windows
    path, so keep only the last path component (both separators), drop control characters, and
    cap the length while keeping the extension.
    """
    name = PureWindowsPath(raw or "").name  # PureWindowsPath splits on both / and \
    name = _CONTROL.sub("", name).strip().strip(".")
    if not name:
        return "untitled"
    if len(name) > FILENAME_MAX:
        stem, dot, ext = name.rpartition(".")
        keep = FILENAME_MAX - len(ext) - 1
        name = f"{stem[:keep]}.{ext}" if dot and len(ext) <= 10 else name[:FILENAME_MAX]
    return name


def file_type_of(filename: str) -> str:
    """The allowed type for this filename's extension, or a 415."""
    ext = filename.rpartition(".")[2].lower() if "." in filename else ""
    if ext not in ALLOWED_TYPES:
        raise UnsupportedFileError(ALLOWED_MESSAGE)
    return ext


def check_content(path: Path, file_type: str) -> None:
    """Does the content match the extension? Raises 415/422 with a message for the user."""
    if path.stat().st_size == 0:
        raise InvalidFileError("The file is empty.")
    with path.open("rb") as f:
        head = f.read(8192)

    if file_type == "pdf":
        # The PDF header must appear within the first 1024 bytes (PDF specification).
        if b"%PDF-" not in head[:1024]:
            raise UnsupportedFileError("This file isn't a PDF, although its name ends in .pdf.")
    elif file_type == "docx":
        _check_docx(path)
    elif b"\x00" in head:
        # Text never contains NUL bytes; binaries (images, executables, .doc) are full of them.
        name = ALLOWED_TYPES[file_type]
        raise UnsupportedFileError(
            f"This doesn't look like a {name} file: it contains binary data."
        )


def _check_docx(path: Path) -> None:
    not_docx = UnsupportedFileError(
        "This file isn't a valid Word document (.docx). Old .doc files aren't supported: "
        "save it as .docx and upload it again."
    )
    if not zipfile.is_zipfile(path):
        raise not_docx
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
    except zipfile.BadZipFile:
        raise not_docx from None
    if "word/document.xml" not in names:
        raise not_docx
    if "word/vbaProject.bin" in names:
        # Macros belong in .docm. We never run them, but a .docx carrying them is mislabelled.
        raise UnsupportedFileError("Word files with macros aren't accepted.")
    if len(entries) > DOCX_MAX_ENTRIES or sum(e.file_size for e in entries) > DOCX_MAX_UNCOMPRESSED:
        raise InvalidFileError("This Word file unpacks to an unreasonably large size.")
