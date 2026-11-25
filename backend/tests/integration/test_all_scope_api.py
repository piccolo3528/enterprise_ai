"""Asking and searching across all of a user's knowledge bases (M16b), end to end: real
full-text search (Neon test branch, rolled back), the real embedding model and Qdrant
("chunks_test"), and the fake LLM of test_conversations_api.

Alice has two knowledge bases (leave; expenses), Bob one whose text is close to Alice's leave
passage, so a leak across owners would show up as Bob's file in Alice's results.
"""

from __future__ import annotations

import pytest

from app.models import Conversation, Message
from tests.helpers import act_as
from tests.integration.test_answer_api import EXPENSES, LEAVE, library
from tests.integration.test_conversations_api import (
    FIRST,
    STANDALONE,
    FakeStreamingLLM,
    parse_events,
    streaming_client,
)
from tests.integration.test_documents_api import documents

pytestmark = pytest.mark.live


@pytest.fixture
def llm():
    return FakeStreamingLLM()


@pytest.fixture
def client(db, tmp_path, vector_store, llm):
    yield from streaming_client(db, tmp_path, vector_store, llm)

BOB_LEAVE = "Unused annual leave can be carried forward by Bob's team, up to twenty days."


@pytest.fixture
def world(client, alice, bob):
    leave_kb = library(client, alice, {"leave.txt": LEAVE})
    money_kb = library(client, alice, {"expenses.txt": EXPENSES})
    bob_kb = library(client, bob, {"bob-leave.txt": BOB_LEAVE})
    act_as(client, bob)
    bob_doc = documents(client, bob_kb)[0]["id"]
    act_as(client, alice)
    names = {kb: client.get(f"/api/knowledge-bases/{kb}").json()["name"]
             for kb in (leave_kb, money_kb)}  # fmt: skip
    return {"leave": leave_kb, "money": money_kb, "bob": bob_kb, "bob_doc": bob_doc,
            "names": names, "alice": alice, "bob_user": bob}  # fmt: skip


def search_all(client, query, **options):
    response = client.post("/api/search", json={"query": query, **options})
    assert response.status_code == 200, response.text
    return response.json()["results"]


def test_search_across_all_finds_every_kb_names_them_and_never_crosses_owners(client, world):
    leave = search_all(client, "annual leave carried forward")
    assert leave[0]["filename"] == "leave.txt"
    expected = (world["leave"], world["names"][world["leave"]])
    assert (leave[0]["kb_id"], leave[0]["kb_name"]) == expected
    money = search_all(client, "travel expenses reimbursed")
    assert money[0]["filename"] == "expenses.txt" and money[0]["kb_id"] == world["money"]
    for query in ("annual leave carried forward", "Bob's team twenty days", "travel expenses"):
        assert "bob-leave.txt" not in {r["filename"] for r in search_all(client, query)}

    act_as(client, world["bob_user"])
    assert {r["filename"] for r in search_all(client, "annual leave carried forward")} == {
        "bob-leave.txt"
    }


def test_a_document_filter_across_all_must_name_one_of_your_documents(client, world):
    response = client.post("/api/search", json={"query": "leave", "document_id": world["bob_doc"]})
    assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"
    act_as(client, world["alice"])
    money_doc = documents(client, world["money"])[0]["id"]
    results = search_all(client, "leave expenses", document_id=money_doc)
    assert {r["filename"] for r in results} == {"expenses.txt"}


def test_an_all_scope_conversation_follows_up_into_another_knowledge_base(client, world, llm, db):
    events = parse_events(client.post("/api/conversations", json={"question": FIRST}))
    conversation_id = events[0][1]["id"]
    first_cites = dict(events)["citations"]
    assert [c["filename"] for c in first_cites] == ["leave.txt"]
    assert first_cites[0]["kb_name"] == world["names"][world["leave"]]

    # The follow-up is rewritten to an expenses question, answered from the OTHER knowledge base.
    llm.cite = "reimbursed"
    follow = client.post(f"/api/conversations/{conversation_id}/messages",
                         json={"question": "And how fast are they paid?"})  # fmt: skip
    cites = dict(parse_events(follow))["citations"]
    assert [c["filename"] for c in cites] == ["expenses.txt"]
    assert cites[0]["kb_name"] == world["names"][world["money"]]

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["kb_id"] is None and len(detail["messages"]) == 4
    assert detail["messages"][2]["rewritten_query"] == STANDALONE  # made standalone first
    listed = [c["id"] for c in client.get("/api/conversations").json()["items"]]
    assert listed == [conversation_id]
    per_kb = client.get(f"/api/knowledge-bases/{world['leave']}/conversations").json()["items"]
    assert per_kb == []  # it belongs to no single knowledge base

    # Deleting one of the knowledge bases keeps the conversation and its saved answers.
    assert client.delete(f"/api/knowledge-bases/{world['leave']}").status_code == 204
    db.expire_all()
    assert db.get(Conversation, conversation_id) is not None
    assert db.query(Message).filter_by(conversation_id=conversation_id).count() == 4


def test_another_user_cant_see_or_continue_an_all_scope_conversation(client, world):
    events = parse_events(client.post("/api/conversations", json={"question": FIRST}))
    conversation_id = events[0][1]["id"]
    act_as(client, world["bob_user"])
    assert client.get("/api/conversations").json()["items"] == []
    assert client.get(f"/api/conversations/{conversation_id}").status_code == 404
    follow = client.post(f"/api/conversations/{conversation_id}/messages",
                         json={"question": "And then?"})  # fmt: skip
    assert follow.status_code == 404
