"""The evaluation's own correctness: metrics against hand-computed values, the chunk -> section
mapping, chunk offsets, and the analysis helpers. A wrong metric would make every later
"improvement" meaningless, so these are checked by hand first."""

from __future__ import annotations

import uuid

import pytest

from app.services.ingestion.base import Block
from app.services.ingestion.chunking import assemble, chunk_document
from evaluation import metrics
from evaluation.analysis import answerability, stale_first, summarize
from evaluation.harness import (
    Answer,
    Hit,
    Question,
    Variant,
    covered_units,
    load_questions,
    section_number,
)
from tests.unit.test_chunking import WORDS

# --- metrics -------------------------------------------------------------------------------------

# Five results; the question's answer is in §4.1 and §3 of document A.
RESULTS = [
    frozenset({"A §1"}),
    frozenset({"B §2"}),
    frozenset({"A §4.1.2", "A §4.2"}),  # a subsection of §4.1: counts
    frozenset(),
    frozenset({"A §3"}),
]
RELEVANT = {"A §4.1", "A §3"}


def test_unit_matching_follows_the_section_tree():
    assert metrics.unit_matches("A §4.1", "A §4.1")
    assert metrics.unit_matches("A §4.1.2", "A §4.1")  # inside it
    assert metrics.unit_matches("A §4.1", "A §4")  # a subsection of a top-level answer
    assert not metrics.unit_matches("A §4", "A §4.1")  # section 4's intro isn't §4.1
    assert not metrics.unit_matches("A §4.10", "A §4.1")  # a prefix of the text, not the tree
    assert not metrics.unit_matches("B §4.1", "A §4.1")  # another document (or version)


def test_metrics_match_hand_computed_values():
    assert metrics.first_relevant_rank(RESULTS, RELEVANT, 5) == 3
    assert [metrics.hit_at_k(RESULTS, RELEVANT, k) for k in (1, 2, 3, 5)] == [0, 0, 1, 1]
    assert metrics.recall_at_k(RESULTS, RELEVANT, 3) == 0.5  # §4.1 found, §3 not yet
    assert metrics.recall_at_k(RESULTS, RELEVANT, 5) == 1.0
    assert metrics.precision_at_k(RESULTS, RELEVANT, 3) == pytest.approx(1 / 3)
    assert metrics.precision_at_k(RESULTS, RELEVANT, 5) == pytest.approx(2 / 5)
    assert metrics.reciprocal_rank(RESULTS, RELEVANT, 5) == pytest.approx(1 / 3)
    assert metrics.reciprocal_rank(RESULTS, RELEVANT, 2) == 0.0


def test_precision_divides_by_k_even_when_fewer_results_came_back():
    assert metrics.precision_at_k([frozenset({"A §3"})], RELEVANT, 5) == pytest.approx(0.2)


def test_recall_needs_relevant_units_and_mean_needs_values():
    with pytest.raises(ValueError):
        metrics.recall_at_k(RESULTS, set(), 5)
    with pytest.raises(ValueError):
        metrics.mean([])


def test_percentile_is_nearest_rank():
    values = [40, 10, 30, 20]
    assert metrics.percentile(values, 50) == 20  # ceil(0.5 * 4) = 2nd smallest
    assert metrics.percentile(values, 95) == 40  # ceil(3.8) = 4th
    assert metrics.percentile(values, 25) == 10
    assert metrics.percentile([5], 50) == 5
    with pytest.raises(ValueError):
        metrics.percentile(values, 0)


def test_best_threshold_by_hand():
    # t=0.6: positives 3/3 right, negatives 0.65 wrong + 0.5 right -> 4/5; t=0.65 and t=0.7
    # also give 4/5; ties prefer the lowest threshold.
    assert metrics.best_threshold([0.8, 0.7, 0.6], [0.65, 0.5]) == (0.6, 0.8)
    # Nothing separates them: "everything negative" (t = inf) can win.
    t, accuracy = metrics.best_threshold([0.1], [0.9, 0.8])
    assert (t, accuracy) == (float("inf"), pytest.approx(2 / 3))


# --- which sections a chunk covers ---------------------------------------------------------------

BLOCKS = [
    Block("Intro.", headings=("Policy",)),
    Block("Leave text.", headings=("Policy", "4. Leave")),
    Block("Annual text.", headings=("Policy", "4. Leave", "4.1 Annual")),
    Block("Sick text.", headings=("Policy", "5. Sick")),
]
ASSEMBLED = assemble(BLOCKS)
TEXT = ASSEMBLED.text


@pytest.mark.parametrize(
    ("headings", "number"),
    [
        (("Policy", "4. Leave", "4.1 Annual"), "4.1"),
        (("Policy", "4. Leave"), "4"),
        (("10. Related Documents",), "10"),
        (("Policy", "4.1.2 Detail"), "4.1.2"),
        (("Policy", "4. Leave", "Notes"), "4"),  # an unnumbered heading inherits its parent's
        (("Policy", "Document Control"), None),
        ((), None),
    ],
)
def test_section_number(headings, number):
    assert section_number(headings) == number


def units(start, end):
    return covered_units(BLOCKS, ASSEMBLED, start, end, "P v1")


def test_a_span_covers_the_sections_whose_body_it_overlaps():
    assert TEXT == (
        "Policy\nIntro.\n\n4. Leave\nLeave text.\n\n4.1 Annual\nAnnual text.\n\n5. Sick\nSick text."
    )
    assert units(0, len(TEXT)) == {"P v1 §4", "P v1 §4.1", "P v1 §5"}  # the intro has no number
    leave = TEXT.index("Leave text.")
    assert units(leave, leave + len("Leave text.")) == {"P v1 §4"}


def test_a_trailing_heading_line_does_not_count():
    # A chunk that ends just after the heading "5. Sick" holds none of §5's text.
    start = TEXT.index("Annual text.")
    end = TEXT.index("Sick text.")
    assert units(start, end) == {"P v1 §4.1"}


@pytest.mark.parametrize("strategy", ["fixed", "overlap", "recursive", "heading"])
def test_chunk_offsets_point_at_the_chunk_body(strategy):
    blocks = [
        Block(" ".join(f"w{i}" for i in range(30)), headings=("Doc", "1. One")),
        Block(" ".join(f"v{i}" for i in range(30)), headings=("Doc", "2. Two")),
    ]
    text = assemble(blocks).text
    drafts = chunk_document(
        blocks, {"document_id": "D", "version": "1"}, WORDS, strategy=strategy, size=12, overlap=3
    )
    assert drafts
    for d in drafts:
        body = text[d.start : d.end]
        assert body and d.text.endswith(body)  # heading-aware adds a header in front


# --- the dataset and the analysis ----------------------------------------------------------------


def test_the_dataset_loads_with_the_expected_shape():
    questions = load_questions()
    assert len(questions) == 57
    scored = [q for q in questions if q.answerable and q.relevant]
    assert len(scored) == 50
    assert all(" v" in u and " §" in u for q in questions for u in q.relevant)


def question(**overrides):
    values = dict(
        id="Q1", text="?", type="factual", answerable=True,
        relevant=frozenset({"HR v3 §4.1"}), expected_documents=frozenset({"HR"}),
        expected_versions=frozenset({"HR v3"}),
    )  # fmt: skip
    return Question(**{**values, **overrides})


def hit(version, units=(), tokens=100, semantic=None):
    return Hit(uuid.uuid4(), 0.5, frozenset(units), version, tokens, semantic)


def answer(q, *hits):
    return Answer(q, Variant("hybrid"), list(hits), {"total": 1.0})


def test_stale_first_flags_an_old_version_shown_before_the_current_one():
    multi = {"HR"}
    old_first = answer(question(), hit("FIN v1"), hit("HR v2"), hit("HR v3", ["HR v3 §4.1"]))
    new_first = answer(question(), hit("HR v3"), hit("HR v2"))
    assert stale_first(old_first, multi) is True
    assert stale_first(new_first, multi) is False
    assert stale_first(answer(question()), multi) is False  # nothing from HR at all
    assert stale_first(new_first, set()) is None  # HR has one version: not applicable


def test_summarize_scores_only_answerable_labelled_questions():
    good = answer(question(id="Q1"), hit("HR v3", ["HR v3 §4.1"], tokens=50))
    bad = answer(question(id="Q2"), hit("HR v2", ["HR v2 §4.1"], tokens=70))
    unanswerable = answer(question(id="Q3", answerable=False, relevant=frozenset()))
    s = summarize([good, bad, unanswerable], {"HR"})
    assert s["questions"] == 2
    assert (s["hit@1"], s["mrr@10"], s["tokens@5"]) == (0.5, 0.5, 60)  # the version matters
    assert s["stale_first"] == (1, 2)


def test_answerability_reports_the_best_threshold():
    yes = [answer(question(id=f"A{i}"), hit("HR v3", semantic=s)) for i, s in enumerate([0.8, 0.7])]
    no = [answer(question(id="N1", answerable=False), hit("HR v3", semantic=0.6))]
    a = answerability(yes + no)
    assert (a["best_threshold"], a["best_accuracy"]) == (0.7, 1.0)
    assert a["unanswerable_scores"] == [("N1", 0.6)]
