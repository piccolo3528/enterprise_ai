"""Chunking strategies (M8). A word-level fake tokenizer makes sizes exact and readable; a few
tests use the real bge tokenizer from the local Hugging Face cache (skipped if not downloaded)."""

from __future__ import annotations

import pathlib
import re

import pytest

from app.services.ingestion.base import Block
from app.services.ingestion.chunking import assemble, chunk_document
from app.services.ingestion.tokens import MAX_CONTENT_TOKENS


class WordTokens:
    """Each run of non-space characters is one token."""

    def offsets(self, text):
        return [m.span() for m in re.finditer(r"\S+", text)]

    def count(self, text):
        return len(self.offsets(text))


WORDS = WordTokens()


def words(n, prefix="w"):
    return " ".join(f"{prefix}{i}" for i in range(n))


def chunk(blocks, strategy, size=10, overlap=0, metadata=None):
    return chunk_document(
        blocks, metadata or {}, WORDS, strategy=strategy, size=size, overlap=overlap
    )


# --- assembling the text ----------------------------------------------------------------------


def test_assemble_writes_headings_where_they_change_and_maps_pages():
    assembled = assemble(
        [
            Block("Intro.", page=1),
            Block("Leave text.", page=2, headings=("Policy", "4. Leave")),
            Block("More leave.", page=2, headings=("Policy", "4. Leave")),
            Block("Sick text.", page=3, headings=("Policy", "5. Sick")),
        ]
    )
    assert assembled.text == (
        "Intro.\n\nPolicy\n4. Leave\nLeave text.\n\nMore leave.\n\n5. Sick\nSick text."
    )
    assert [s.page for s in assembled.segments] == [1, 2, 2, 3]
    assert assembled.segment_at(assembled.text.index("Sick text")).headings == ("Policy", "5. Sick")


# --- fixed and overlapping windows ------------------------------------------------------------


def test_fixed_windows_cover_every_token_exactly_once():
    chunks = chunk([Block(words(25))], "fixed", size=10)
    assert [c.token_count for c in chunks] == [10, 10, 5]
    assert " ".join(c.text for c in chunks) == words(25)


def test_overlapping_windows_share_exactly_the_overlap():
    chunks = chunk([Block(words(22))], "overlap", size=10, overlap=4)
    texts = [c.text.split() for c in chunks]
    assert [len(t) for t in texts] == [10, 10, 10]  # starts at 0, 6, 12; the last reaches w21
    for previous, current in zip(texts, texts[1:], strict=False):
        assert previous[-4:] == current[:4]
    assert texts[-1][-1] == "w21"


# --- recursive --------------------------------------------------------------------------------


def test_recursive_keeps_paragraphs_whole_when_they_fit():
    paragraphs = [words(6, "a"), words(3, "b"), words(7, "c")]
    chunks = chunk([Block("\n\n".join(paragraphs))], "recursive", size=10)
    assert [c.text for c in chunks] == [f"{paragraphs[0]}\n\n{paragraphs[1]}", paragraphs[2]]


def test_recursive_splits_a_long_paragraph_at_sentences_then_words():
    sentences = [f"{words(4, f's{i}x')}." for i in range(5)]  # five 4-word sentences
    long_sentence = words(23, "z")  # no sentence break at all
    chunks = chunk([Block(" ".join(sentences) + "\n\n" + long_sentence)], "recursive", size=10)
    assert all(c.token_count <= 10 for c in chunks)
    assert chunks[0].text == f"{sentences[0]} {sentences[1]}"  # whole sentences, 8 tokens
    assert (
        " ".join(c.text for c in chunks).split()
        == (" ".join(sentences) + " " + long_sentence).split()
    )


def test_recursive_overlap_repeats_whole_trailing_sentences():
    sentences = [f"{words(3, f's{i}x')}." for i in range(6)]  # six 3-word sentences
    chunks = chunk([Block(" ".join(sentences))], "recursive", size=9, overlap=3)
    assert chunks[0].text == " ".join(sentences[:3])
    assert chunks[1].text.startswith(sentences[2])  # last sentence carried over, whole


# --- heading-aware ------------------------------------------------------------------------------

POLICY = [
    Block("Owner: HR.", headings=("Leave Policy",)),
    Block(words(4, "a"), headings=("Leave Policy", "4. Entitlements", "4.1 Annual")),
    Block(words(3, "b"), headings=("Leave Policy", "4. Entitlements", "4.2 Carry")),
    Block(words(30, "c"), headings=("Leave Policy", "4. Entitlements", "4.3 Long")),
    Block(words(2, "d"), headings=("Leave Policy", "5. Sick")),
]


def test_heading_chunks_never_cross_a_top_level_section_and_merge_small_siblings():
    # Heading lines count too: 4.1 is 8 tokens ("4. Entitlements 4.1 Annual" + 4 words), 4.2 is 5.
    chunks = chunk(
        POLICY, "heading", size=14, metadata={"document_id": "NX-HR-002", "version": "3.0"}
    )
    sections = [c.section for c in chunks]
    # 4.1 and 4.2 are merged (13 <= 14); the 30-word 4.3 is split recursively; 5. stays alone.
    assert sections[1] == "4. Entitlements › 4.1 Annual – 4.2 Carry"
    assert all(s.startswith("4. Entitlements › 4.3 Long") for s in sections[2:-1])
    assert sections[-1] == "5. Sick"
    assert all("d0" not in c.text for c in chunks[:-1])  # section 5 text is only in its own chunk
    # The document title is dropped from section labels but the header names the document.
    assert chunks[1].text.startswith(
        "NX-HR-002 v3.0 · 4. Entitlements › 4.1 Annual – 4.2 Carry\n\n"
    )


def test_auto_uses_headings_when_there_are_some_and_recursive_otherwise():
    assert {c.strategy for c in chunk(POLICY, "auto", size=12)} == {"heading"}
    assert {c.strategy for c in chunk([Block(words(30))], "auto")} == {"recursive"}


# --- what every strategy guarantees ---------------------------------------------------------


@pytest.mark.parametrize("strategy", ["fixed", "overlap", "recursive", "heading"])
def test_every_strategy_is_deterministic_ordered_and_has_no_empty_chunks(strategy):
    blocks = [*POLICY, Block("   "), Block(words(15, "e"), headings=("Leave Policy", "6. Other"))]
    first = chunk(blocks, strategy, size=12, overlap=3)
    assert first == chunk(blocks, strategy, size=12, overlap=3)
    assert [c.index for c in first] == list(range(len(first)))
    assert all(c.text.strip() and c.text == c.text.strip() for c in first)


@pytest.mark.parametrize("strategy", ["fixed", "overlap", "recursive"])
def test_pdf_chunks_know_their_page_span(strategy):
    # 5 words per page: two pages fit in 12 tokens, so some chunk must span a page boundary
    # (recursive keeps each page's paragraph whole, so with 8-word pages none would).
    pages = [Block(words(5, f"p{n}x"), page=n) for n in (1, 2, 3)]
    chunks = chunk(pages, strategy, size=12, overlap=2)
    assert chunks[0].page_start == 1
    assert any(c.page_start != c.page_end for c in chunks)  # some chunk spans two pages
    for c in chunks:
        on_pages = {int(w[1]) for w in c.text.split()}  # "p2x5" -> page 2
        assert on_pages == set(range(c.page_start, c.page_end + 1))


def test_nothing_ever_exceeds_the_models_limit():
    chunks = chunk([Block(words(2000))], "recursive", size=900)  # asked for more than allowed
    assert max(c.token_count for c in chunks) <= MAX_CONTENT_TOKENS


def test_an_unknown_strategy_is_an_error():
    with pytest.raises(ValueError, match="unknown chunking strategy"):
        chunk([Block("x")], "magic")


# --- with the real tokenizer ----------------------------------------------------------------


@pytest.fixture(scope="module")
def bge():
    from app.services.ingestion.tokens import HuggingFaceTokens

    try:
        return HuggingFaceTokens("BAAI/bge-small-en-v1.5", local_only=True)
    except Exception:  # noqa: BLE001 - not downloaded on this machine
        pytest.skip("bge-small tokenizer isn't in the local Hugging Face cache")


def test_a_real_policy_chunks_within_limits_with_sections(bge):
    from app.services.ingestion.extractors import extract

    source = next(pathlib.Path("evaluation/corpus/hr").glob("NX-HR-002*v3.0.md"))
    extraction = extract(source, "md")
    chunks = chunk_document(extraction.blocks, extraction.metadata, bge, size=400, overlap=60)
    assert {c.strategy for c in chunks} == {"heading"}
    assert all(c.token_count == bge.count(c.text) <= MAX_CONTENT_TOKENS for c in chunks)
    assert all(c.text.startswith("NX-HR-002 v3.0") for c in chunks)
    assert sum(1 for c in chunks if c.section) >= len(chunks) - 2  # only the front matter part
    # Every word of the document is in some chunk.
    all_text = " ".join(c.text for c in chunks)
    assert all(b.text.split()[0] in all_text for b in extraction.blocks)
