"""VectorStore against qdrant-client's in-memory mode: the same API as the server, no network.

(Payload indexes are accepted but have no effect in memory; the live tests use the real cluster.)
"""

from __future__ import annotations

import uuid

import pytest
from qdrant_client import QdrantClient, models

from app.services.vector_store import (
    PAYLOAD_INDEXES,
    UPSERT_BATCH,
    ChunkPoint,
    VectorStore,
    VectorStoreConfigError,
)

DIM = 4

# Expected in memory (see the module docstring); the live tests cover real indexes.
pytestmark = pytest.mark.filterwarnings("ignore:Payload indexes have no effect:UserWarning")


@pytest.fixture
def store():
    client = QdrantClient(location=":memory:")
    yield VectorStore(client, "chunks")
    client.close()


def point(kb_id, document_id, owner_id, vector=(1.0, 0.0, 0.0, 0.0), index=0) -> ChunkPoint:
    return ChunkPoint(
        uuid.uuid4(),
        list(vector),
        {
            "kb_id": str(kb_id),
            "document_id": str(document_id),
            "owner_id": str(owner_id),
            "chunk_index": index,
        },
    )


def test_the_collection_is_created_once_with_cosine_distance(store):
    assert store.ensure_collection(DIM) is True
    assert store.ensure_collection(DIM) is False  # remembered: no second request
    params = store.client.get_collection("chunks").config.params.vectors
    assert (params.size, params.distance) == (DIM, models.Distance.COSINE)
    # Every field a filter uses is indexed (Qdrant Cloud's strict mode refuses the rest).
    assert set(PAYLOAD_INDEXES) == {"kb_id", "owner_id", "document_id", "doc_status"}


def test_an_existing_collection_of_another_dimension_is_refused(store):
    store.client.create_collection(
        "chunks", vectors_config=models.VectorParams(size=8, distance=models.Distance.COSINE)
    )
    with pytest.raises(VectorStoreConfigError, match="reindex"):
        store.ensure_collection(DIM)


def test_upsert_in_batches_then_count_by_kb_and_document(store):
    store.ensure_collection(DIM)
    kb, other_kb, doc, owner = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    many = [point(kb, doc, owner, index=i) for i in range(UPSERT_BATCH + 5)]  # two batches
    store.upsert([*many, point(other_kb, uuid.uuid4(), owner)])
    assert store.count() == UPSERT_BATCH + 6
    assert store.count(kb_id=kb) == store.count(document_id=doc) == UPSERT_BATCH + 5
    assert store.points_per_document()[str(doc)] == UPSERT_BATCH + 5


def test_upserting_the_same_id_overwrites_instead_of_duplicating(store):
    store.ensure_collection(DIM)
    p = point(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    store.upsert([p])
    store.upsert([p])
    assert store.count() == 1


def test_delete_document_can_keep_the_fresh_points(store):
    """A reprocess writes the new points first, then removes everything else of the document."""
    store.ensure_collection(DIM)
    kb, doc, owner = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    old = [point(kb, doc, owner, index=i) for i in range(3)]
    new = [point(kb, doc, owner, index=i) for i in range(2)]
    neighbour = point(kb, uuid.uuid4(), owner)
    store.upsert([*old, *new, neighbour])
    store.delete_document(doc, keep=[p.id for p in new])
    remaining = {str(p.id) for p in store.client.scroll("chunks", limit=100)[0]}
    assert remaining == {str(p.id) for p in [*new, neighbour]}
    store.delete_document(doc)
    assert store.count(document_id=doc) == 0 and store.count() == 1


def test_delete_knowledge_base_removes_only_that_knowledge_base(store):
    store.ensure_collection(DIM)
    kb, other_kb, owner = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    store.upsert([point(kb, uuid.uuid4(), owner), point(other_kb, uuid.uuid4(), owner)])
    store.delete_knowledge_base(kb)
    assert (store.count(kb_id=kb), store.count(kb_id=other_kb)) == (0, 1)


def test_deleting_or_counting_without_a_collection_is_a_no_op(store):
    store.delete_document(uuid.uuid4())
    store.delete_knowledge_base(uuid.uuid4())
    assert store.count() == 0 and store.points_per_document() == {}


def test_search_needs_owner_and_kb_and_ranks_by_cosine(store):
    store.ensure_collection(DIM)
    kb, doc, alice, bob = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    near = point(kb, doc, alice, vector=(1.0, 0.1, 0.0, 0.0))
    far = point(kb, doc, alice, vector=(0.0, 1.0, 0.0, 0.0))
    elsewhere = point(uuid.uuid4(), uuid.uuid4(), alice, vector=(1.0, 0.0, 0.0, 0.0))
    store.upsert([near, far, elsewhere])

    hits = store.search([1.0, 0.0, 0.0, 0.0], owner_id=alice, kb_id=kb, limit=5)
    assert [h.chunk_id for h in hits] == [near.id, far.id]  # closest first, other KB excluded
    assert hits[0].score == pytest.approx(1 / (1 + 0.01) ** 0.5, abs=1e-6)  # the cosine
    assert hits[1].score == pytest.approx(0.0, abs=1e-6)
    # Right knowledge base, wrong owner: nothing.
    assert store.search([1.0, 0.0, 0.0, 0.0], owner_id=bob, kb_id=kb, limit=5) == []
    # Narrowed to one document.
    other = store.search([1, 0, 0, 0], owner_id=alice, kb_id=kb, limit=5, document_id=uuid.uuid4())
    assert other == []


def test_recreate_empties_the_collection(store):
    store.ensure_collection(DIM)
    store.upsert([point(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())])
    store.recreate(DIM)
    assert store.count() == 0
    assert store.client.collection_exists("chunks")
