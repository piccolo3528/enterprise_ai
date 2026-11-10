"""Upload validation, text extraction and cleaning, on generated files (no network, no DB)."""

from __future__ import annotations

import io
import uuid

import pytest

from app.core.errors import InvalidFileError, PayloadTooLargeError, UnsupportedFileError
from app.services.ingestion.base import ExtractionError
from app.services.ingestion.cleaning import clean_text, join_wrapped_lines
from app.services.ingestion.extractors import NO_TEXT, extract, split_front_matter
from app.services.ingestion.validation import check_content, display_filename, file_type_of
from app.services.storage import Storage
from tests import sample_files


def write(tmp_path, name: str, data: bytes):
    path = tmp_path / name
    path.write_bytes(data)
    return path


# --- filenames and types -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("policy.pdf", "policy.pdf"),
        ("..\\..\\windows\\system32\\evil.pdf", "evil.pdf"),
        ("../../etc/passwd.txt", "passwd.txt"),
        ("C:\\Users\\ana\\Desktop\\Leave Policy.docx", "Leave Policy.docx"),
        ("bad\x00name\x1b.md", "badname.md"),
        ("", "untitled"),
        (None, "untitled"),
    ],
)
def test_only_the_bare_filename_is_kept(raw, expected):
    assert display_filename(raw) == expected


def test_long_filenames_keep_their_extension():
    name = display_filename("x" * 400 + ".pdf")
    assert len(name) == 255 and name.endswith(".pdf")


@pytest.mark.parametrize("name", ["a.PDF", "b.Docx", "c.txt", "d.md"])
def test_allowed_extensions_any_case(name):
    assert file_type_of(name) == name.rpartition(".")[2].lower()


@pytest.mark.parametrize("name", ["a.doc", "b.docm", "c.exe", "d.pdf.exe", "noextension", "e.html"])
def test_other_extensions_are_refused(name):
    with pytest.raises(UnsupportedFileError, match="Only PDF, Word"):
        file_type_of(name)


# --- content must match the extension ------------------------------------------------------------


def test_real_files_pass(tmp_path):
    check_content(write(tmp_path, "a.pdf", sample_files.pdf("Hello")), "pdf")
    check_content(write(tmp_path, "b.docx", sample_files.docx(("p", "Hello"))), "docx")
    check_content(write(tmp_path, "c.txt", "Grüße, día".encode("cp1252")), "txt")
    check_content(write(tmp_path, "d.md", b"# Title"), "md")


@pytest.mark.parametrize(
    ("name", "file_type", "data", "message"),
    [
        ("fake.pdf", "pdf", b"MZ\x90\x00 an executable", "isn't a PDF"),
        ("fake.docx", "docx", b"%PDF-1.7 a pdf in disguise", "isn't a valid Word"),
        ("old.docx", "docx", b"\xd0\xcf\x11\xe0 a legacy .doc", "Old .doc files"),
        ("image.txt", "txt", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "binary data"),
    ],
)
def test_a_fake_extension_is_refused(tmp_path, name, file_type, data, message):
    with pytest.raises(UnsupportedFileError, match=message):
        check_content(write(tmp_path, name, data), file_type)


def test_a_zip_that_is_not_word_is_refused(tmp_path):
    buffer = io.BytesIO()
    import zipfile

    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "hello")
    with pytest.raises(UnsupportedFileError, match="isn't a valid Word"):
        check_content(write(tmp_path, "x.docx", buffer.getvalue()), "docx")


def test_a_zip_bomb_is_refused_before_unpacking(tmp_path):
    data = sample_files.zip_bomb_docx()
    assert len(data) < 1024 * 1024  # under 1 MB on disk...
    with pytest.raises(InvalidFileError, match="unreasonably large"):  # ...300 MB unpacked
        check_content(write(tmp_path, "bomb.docx", data), "docx")


def test_an_empty_file_is_refused(tmp_path):
    with pytest.raises(InvalidFileError, match="empty"):
        check_content(write(tmp_path, "e.txt", b""), "txt")


# --- storage -------------------------------------------------------------------------------------


def test_storage_hashes_while_saving_and_uses_server_names(tmp_path):
    storage = Storage(tmp_path)
    kb_id, doc_id = uuid.uuid4(), uuid.uuid4()
    saved = storage.save_partial(io.BytesIO(b"abc"), kb_id, doc_id, "txt", max_bytes=10)
    assert saved.size_bytes == 3
    assert saved.sha256 == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert saved.relative_path == f"{kb_id}/{doc_id}.txt"
    storage.promote(saved)
    assert (tmp_path / str(kb_id) / f"{doc_id}.txt").read_bytes() == b"abc"
    assert not saved.partial.exists()


def test_storage_stops_at_the_size_limit_and_leaves_nothing(tmp_path):
    storage = Storage(tmp_path)
    with pytest.raises(PayloadTooLargeError):
        storage.save_partial(io.BytesIO(b"x" * 11), uuid.uuid4(), uuid.uuid4(), "txt", 10)
    assert not any(p.is_file() for p in tmp_path.rglob("*"))


def test_storage_never_follows_a_path_outside_its_folder(tmp_path):
    with pytest.raises(ValueError):
        Storage(tmp_path / "uploads").path_of("../outside.txt")


# --- cleaning ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("ﬁnance and ﬂow", "finance and flow"),  # ligatures
        ("infor-\nmation", "information"),  # word hyphenated across a line break
        ("COVID-\n19", "COVID-\n19"),  # not a word break: left alone
        ("a\u00a0b\u2009c", "a b c"),  # no-break and thin spaces
        ("zero\u200bwidth\ufeff soft\u00adhyphen", "zerowidth softhyphen"),
        ("bell\x07 and nul\x00", "bell and nul"),
        ("too    many   spaces  \n  trailing  ", "too many spaces\ntrailing"),
        ("a\n\n\n\n\nb", "a\n\nb"),
        ("Cafe\u0301", "Café"),  # decomposed accent -> one character (NFC)
        ("½ day, 10 m²", "½ day, 10 m²"),  # NFC, not NFKC: meaningful characters survive
        ("windows\r\nline\rends", "windows\nline\nends"),
    ],
)
def test_clean_text(raw, clean):
    assert clean_text(raw) == clean


def test_wrapped_pdf_lines_become_one_paragraph():
    assert join_wrapped_lines("Employees re-\nceive 24 days\nof leave.\n") == (
        "Employees receive 24 days of leave."
    )


# --- extraction ----------------------------------------------------------------------------------


def test_pdf_text_per_page(tmp_path):
    path = write(
        tmp_path,
        "p.pdf",
        sample_files.pdf("Page one talks about finance.", "", "Page three: annual leave."),
    )
    result = extract(path, "pdf")
    assert result.page_count == 3
    assert [(b.page, b.text) for b in result.blocks] == [
        (1, "Page one talks about finance."),
        (3, "Page three: annual leave."),  # the blank (scanned-like) page 2 is skipped
    ]


def test_a_pdf_with_no_text_says_ocr_is_not_supported(tmp_path):
    with pytest.raises(ExtractionError) as info:
        extract(write(tmp_path, "scan.pdf", sample_files.pdf("", "")), "pdf")
    assert info.value.message == NO_TEXT and "OCR" in NO_TEXT


def test_an_encrypted_pdf_asks_for_the_password_to_be_removed(tmp_path):
    data = sample_files.pdf("secret", password="pw-123")
    with pytest.raises(ExtractionError, match="password-protected"):
        extract(write(tmp_path, "locked.pdf", data), "pdf")


def test_a_damaged_pdf_fails_with_a_plain_message(tmp_path):
    data = sample_files.pdf("Hello world")
    damaged = data[:20] + b"\x00garbage\xff" * 40  # valid header, broken body
    with pytest.raises(ExtractionError, match="damaged"):
        extract(write(tmp_path, "broken.pdf", damaged), "pdf")


def test_docx_keeps_headings_and_tables_in_document_order(tmp_path):
    data = sample_files.docx(
        ("h1", "Leave Policy"),
        ("p", "Applies to all staff."),
        ("h2", "4.2 Annual leave"),
        ("p", "Employees receive 24 days."),
        ("table", [["Grade", "Days"], ["A", "24"], ["B", "26"]]),
        ("h2", "4.3 Sick leave"),
        ("p", "Up to 10 days."),
    )
    result = extract(write(tmp_path, "l.docx", data), "docx")
    assert result.page_count is None  # DOCX has no pages (L15)
    assert [(b.headings, b.text) for b in result.blocks] == [
        (("Leave Policy",), "Applies to all staff."),
        (
            ("Leave Policy", "4.2 Annual leave"),
            "Employees receive 24 days.\nGrade | Days\nA | 24\nB | 26",
        ),
        (("Leave Policy", "4.3 Sick leave"), "Up to 10 days."),
    ]


def test_a_damaged_docx_fails_with_a_plain_message(tmp_path):
    data = sample_files.docx(("p", "Hello"))
    with pytest.raises(ExtractionError, match="damaged"):
        extract(write(tmp_path, "broken.docx", data[: len(data) // 2]), "docx")


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "cp1252"])
def test_txt_in_common_encodings(tmp_path, encoding):
    text = "Grüße aus München: café, naïve, déjà vu. " * 5
    result = extract(write(tmp_path, "t.txt", text.encode(encoding)), "txt")
    assert result.blocks[0].text == text.strip()


def test_short_western_text_in_cp1252_is_not_misdetected(tmp_path):
    # Found while testing: statistical detection guessed cp852 for this, garbling the quotes.
    text = "The employee’s “annual leave” – 24 days, €200 allowance."
    assert extract(write(tmp_path, "w.txt", text.encode("cp1252")), "txt").blocks[0].text == text


def test_non_latin_legacy_text_falls_back_to_detection(tmp_path):
    text = "Сотрудники получают 24 дня ежегодного отпуска. Политика компании. " * 3
    result = extract(write(tmp_path, "ru.txt", text.encode("cp1251")), "txt")
    assert result.blocks[0].text == text.strip()


def test_an_empty_text_file_has_nothing_to_extract(tmp_path):
    with pytest.raises(ExtractionError, match="No text"):
        extract(write(tmp_path, "blank.txt", b"   \n\n \t "), "txt")


def test_markdown_front_matter_and_heading_paths(tmp_path):
    result = extract(write(tmp_path, "p.md", sample_files.MARKDOWN.encode()), "md")
    assert result.metadata == {
        "document_id": "NX-HR-002",
        "title": "Annual Leave Policy",
        "version": "3.0",
        "status": "current",  # lower-cased and checked against the allowed values
        "effective_date": "2026-01-01",  # YAML date -> ISO text
        "amended_by": [],
        "related_documents": ["NX-HR-001", "NX-GOV-001"],
        # owner_email and nested were dropped: not in the allowed keys
    }
    assert [(b.headings, b.text.split("\n")[0]) for b in result.blocks] == [
        (("Annual Leave Policy",), "Intro paragraph."),
        (
            ("Annual Leave Policy", "4. Leave Types", "4.2 Annual leave"),
            "Employees receive 24 days of annual leave.",
        ),  # noqa: E501
        (("Annual Leave Policy", "4. Leave Types", "4.3 Sick leave"), "Up to 10 days."),
    ]
    # The "# not a heading" line inside the code block stayed in the text.
    assert "# not a heading" in result.blocks[1].text


def test_front_matter_cannot_build_python_objects():
    # yaml.load would construct the object; safe_load refuses the tag.
    with pytest.raises(ExtractionError, match="isn't valid YAML"):
        split_front_matter("---\nx: !!python/object/apply:os.system ['echo hacked']\n---\nBody")


def test_unknown_status_is_dropped_and_a_rule_line_is_not_front_matter():
    metadata, _ = split_front_matter("---\nstatus: secret-ish\nversion: 2\n---\n")
    assert metadata == {"version": "2"}
    assert split_front_matter("---\njust a horizontal rule, never closed") == (
        {},
        "---\njust a horizontal rule, never closed",
    )
