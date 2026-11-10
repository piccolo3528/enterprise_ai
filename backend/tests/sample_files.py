"""Test documents, generated in code so the repository holds no binary fixtures.

Every builder returns bytes, so a test can write them to a temporary folder or upload them.
"""

from __future__ import annotations

import io
import zipfile

import pymupdf
from docx import Document


def pdf(*pages: str, password: str | None = None) -> bytes:
    """A PDF with one page per string. An empty string makes a page with no text at all, which
    is what a scanned page (a picture) looks like to a text extractor."""
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        if text:
            # insert_textbox wraps the text inside the rectangle, like a real paragraph.
            page.insert_textbox(pymupdf.Rect(72, 72, 520, 770), text, fontsize=11)
    options = {}
    if password:
        options = {
            "encryption": pymupdf.PDF_ENCRYPT_AES_256,
            "user_pw": password,
            "owner_pw": password,
        }
    data = document.tobytes(**options)
    document.close()
    return data


def docx(*items: tuple[str, str | list[list[str]]]) -> bytes:
    """Items in order: ("h1"/"h2"/"h3", text), ("p", text) or ("table", rows)."""
    document = Document()
    for kind, content in items:
        if kind.startswith("h"):
            document.add_heading(content, level=int(kind[1]))
        elif kind == "p":
            document.add_paragraph(content)
        elif kind == "table":
            table = document.add_table(rows=len(content), cols=len(content[0]))
            for r, row in enumerate(content):
                for c, value in enumerate(row):
                    table.cell(r, c).text = value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def zip_bomb_docx() -> bytes:
    """A tiny archive that claims to unpack to ~300 MB (highly compressible zeros)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
        with archive.open("word/media/huge.bin", "w") as member:  # streamed: no 300 MB in RAM
            block = b"\x00" * (1024 * 1024)
            for _ in range(300):
                member.write(block)
    return buffer.getvalue()


MARKDOWN = """---
document_id: NX-HR-002
title: Annual Leave Policy
version: "3.0"
status: Current
effective_date: 2026-01-01
amended_by: []
related_documents: [NX-HR-001, NX-GOV-001]
owner_email: someone@example.com
nested: {a: 1}
---

# Annual Leave Policy

Intro paragraph.

## 4. Leave Types

### 4.2 Annual leave

Employees receive 24 days of annual leave.

```bash
# not a heading: inside a code block
echo hello
```

### 4.3 Sick leave

Up to 10 days.
"""
