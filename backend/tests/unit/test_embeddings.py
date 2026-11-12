"""Embeddings: cosine similarity by hand, the query-only prefix, and the real model on CPU."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.services.embeddings import (
    BGE_QUERY_PREFIX,
    Embedder,
    cosine_similarity,
    load_embedder,
    query_prefix_for,
)

MODEL = "BAAI/bge-small-en-v1.5"

# --- cosine similarity, by hand ---------------------------------------------------------------


def test_cosine_of_hand_computed_vectors():
    # a·b = 1*2 + 2*0 + 2*1 = 4;  |a| = 3, |b| = sqrt(5)
    assert cosine_similarity([1, 2, 2], [2, 0, 1]) == pytest.approx(4 / (3 * math.sqrt(5)))


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ([1, 0], [5, 0], 1.0),  # same direction, any length
        ([1, 0], [0, 3], 0.0),  # orthogonal: unrelated
        ([1, 2], [-2, -4], -1.0),  # opposite
    ],
)
def test_cosine_depends_on_the_angle_only(a, b, expected):
    assert cosine_similarity(a, b) == pytest.approx(expected)


def test_cosine_rejects_zero_and_mismatched_vectors():
    with pytest.raises(ValueError, match="zero vector"):
        cosine_similarity([0, 0], [1, 0])
    with pytest.raises(ValueError, match="different lengths"):
        cosine_similarity([1, 0], [1, 0, 0])


# --- the Embedder, with a fake model that records what it was given --------------------------


class FakeModel:
    def __init__(self):
        self.calls = []

    def get_embedding_dimension(self):
        return 3

    def encode(self, sentences, **kwargs):
        self.calls.append((list(sentences), kwargs))
        return np.array([[float(len(s)), 0.0, 0.0] for s in sentences])


def test_the_prefix_goes_on_queries_and_never_on_documents():
    model = FakeModel()
    embedder = Embedder(model, query_prefix=BGE_QUERY_PREFIX, batch_size=4)
    embedder.embed_documents(["Annual leave is 24 days.", "Sick leave is 10 days."])
    embedder.embed_query("how much annual leave?")
    (documents, options), (queries, _) = model.calls
    assert documents == ["Annual leave is 24 days.", "Sick leave is 10 days."]
    assert queries == [BGE_QUERY_PREFIX + "how much annual leave?"]
    assert options["normalize_embeddings"] is True
    assert options["batch_size"] == 4


def test_vectors_come_back_as_plain_lists_and_nothing_is_encoded_for_no_texts():
    model = FakeModel()
    embedder = Embedder(model)
    assert embedder.dimension == 3
    assert embedder.embed_documents([]) == [] and model.calls == []
    (vector,) = embedder.embed_documents(["abc"])
    assert vector == [3.0, 0.0, 0.0] and isinstance(vector[0], float)


@pytest.mark.parametrize(
    ("model_name", "prefix"),
    [
        ("BAAI/bge-small-en-v1.5", BGE_QUERY_PREFIX),
        ("BAAI/bge-base-en-v1.5", BGE_QUERY_PREFIX),
        ("BAAI/bge-m3", ""),  # multilingual BGE: no instruction
        ("sentence-transformers/all-MiniLM-L6-v2", ""),
    ],
)
def test_only_english_bge_models_get_the_query_prefix(model_name, prefix):
    assert query_prefix_for(model_name) == prefix


# --- the real model (from the local Hugging Face cache; never the network) --------------------


@pytest.fixture(scope="module")
def bge():
    try:
        return load_embedder(MODEL, local_only=True)
    except Exception:  # noqa: BLE001
        pytest.skip("bge-small is not cached: run scripts/download_models.py")


QUERY = "How many days of unused leave can be carried forward?"
RELEVANT = "Employees may carry forward up to 10 days of unused annual leave into the next year."
UNRELATED = "Expense claims must be submitted within 30 days of the expense."


def test_real_vectors_are_384_numbers_of_length_one(bge):
    vectors = bge.embed_documents([RELEVANT, UNRELATED])
    assert bge.dimension == 384
    assert [len(v) for v in vectors] == [384, 384]
    assert [math.hypot(*v) for v in vectors] == pytest.approx([1.0, 1.0], abs=1e-5)


def test_for_normalized_vectors_cosine_equals_the_dot_product(bge):
    query = bge.embed_query(QUERY)
    relevant, unrelated = bge.embed_documents([RELEVANT, UNRELATED])
    dot = sum(q * r for q, r in zip(query, relevant, strict=True))
    assert cosine_similarity(query, relevant) == pytest.approx(dot, abs=1e-6)
    # ...and meaning is captured: the relevant passage is clearly closer.
    assert cosine_similarity(query, relevant) > cosine_similarity(query, unrelated) + 0.1


def test_the_query_prefix_changes_the_query_vector(bge):
    with_prefix = bge.embed_query(QUERY)
    (without,) = bge.embed_documents([QUERY])
    assert cosine_similarity(with_prefix, without) < 0.99  # a different point in space
