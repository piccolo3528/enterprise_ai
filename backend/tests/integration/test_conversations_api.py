"""Conversations end to end with a **fake streaming LLM** (M13): real uploads, chunking,
embeddings, Qdrant ("chunks_test") and PostgreSQL (Neon test branch, rolled back). Checks the SSE
event order, what is saved, follow-up rewriting, and that nobody sees anyone else's conversations.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.api.deps import (
    get_db,
    get_llm,
    get_read_db,
    get_read_session_factory,
    get_session_factory,
    get_vector_store,
)
from app.core.errors import LLMUnavailableError
from app.factory import create_app
from app.models import Conversation, Message
from app.services import rag
from app.services.llm.base import LLMResult
from app.services.llm.prompts import REWRITE_SYSTEM_PROMPT, SYSTEM_PROMPT
from tests.helpers import act_as, live_settings
from tests.integration.test_answer_api import EXPENSES, LEAVE, library
from tests.integration.test_documents_api import documents, new_kb

pytestmark = pytest.mark.live

FIRST = "How much annual leave can be carried forward?"
FOLLOW_UP = "And how fast are they reimbursed?"
STANDALONE = "How fast are travel expenses reimbursed?"


class FakeStreamingLLM:
    """Cites the source containing `cite` (or replies NOT_FOUND), streamed in two pieces.
    Rewrites any follow-up to `standalone`. Records every call."""

    model = "fake-llm"

    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []  # (kind, system, prompt)
        self.cite = "carried forward"
        self.standalone = STANDALONE
        self.phrasings = ["reimbursement of travel expenses after receipts"]
        self.fail: Exception | None = None

    def generate(self, *, system, prompt, model=None, json_schema=None, max_output_tokens=None):
        if "search_queries" in (json_schema or {}).get("properties", {}):  # M14 planning call
            self.calls.append(("plan", system, prompt))
            question = re.search(r"<question>\n(.*)\n</question>", prompt, re.S).group(1)
            first = "<conversation>\n\n</conversation>" in prompt
            reply = {"standalone_question": question if first else self.standalone,
                     "search_queries": self.phrasings}  # fmt: skip
            return LLMResult(json.dumps(reply), "fake-1", "stop")
        self.calls.append(("rewrite", system, prompt))
        return LLMResult(json.dumps({"standalone_question": self.standalone}), "fake-1", "stop")

    def stream(self, *, system, prompt):
        self.calls.append(("answer", system, prompt))
        reply = "NOT_FOUND"
        for number, text in re.findall(r'<source id="(\d+)"[^>]*>\n(.*?)\n</source>', prompt, re.S):
            if self.cite in text:
                reply = f"The answer is in the policy [{number}]."
                break
        half = len(reply) // 2
        yield reply[:half]
        if self.fail:
            raise self.fail
        yield reply[half:]
        yield LLMResult(reply, "fake-llm-1", "stop", 500, 8, 1, {"first_token": 1.0})


@pytest.fixture
def llm():
    return FakeStreamingLLM()


class KeepOpen:
    """The test session, shared by every request. The streaming routes close their read session
    before streaming (to release the connection); closing the shared one would roll back its
    savepoint and expire the fixtures' rows, so here close() does nothing."""

    def __init__(self, db):
        self._db = db

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._db, name)


@pytest.fixture
def client(db, tmp_path, vector_store, llm):
    yield from streaming_client(db, tmp_path, vector_store, llm)


def streaming_client(db, tmp_path, vector_store, llm):
    """The app with the test session, the test collection and `llm`; shared with
    test_all_scope_api.py (M16b), whose fixtures call it."""
    # M13 behaviour by default (no planning call on first questions); M14's test turns it on
    settings = live_settings(upload_dir=tmp_path / "uploads", multi_query_enabled=False)
    app = create_app(settings, warm_up=False)

    @contextmanager
    def shared_session():
        yield db

    app.dependency_overrides[get_vector_store] = lambda: vector_store
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_read_db] = lambda: KeepOpen(db)
    app.dependency_overrides[get_session_factory] = lambda: shared_session
    app.dependency_overrides[get_read_session_factory] = lambda: shared_session
    app.dependency_overrides[get_llm] = lambda: llm
    with TestClient(app, base_url="https://testserver") as c:
        c.secret = settings.jwt_secret.get_secret_value()
        c.app_ = app
        c.settings_ = settings
        yield c


def parse_events(response) -> list[tuple[str, object]]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    events = []
    for block in response.text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def start(client, kb_id, question=FIRST):
    return parse_events(
        client.post(f"/api/knowledge-bases/{kb_id}/conversations", json={"question": question})
    )


def follow_up(client, conversation_id, question=FOLLOW_UP):
    return parse_events(
        client.post(f"/api/conversations/{conversation_id}/messages", json={"question": question})
    )


def names(events):
    return [name for name, _ in events]


def test_a_first_question_streams_and_creates_the_conversation(client, alice, llm):
    kb_id = library(client, alice, {"leave.txt": LEAVE, "expenses.txt": EXPENSES})
    events = start(client, kb_id)
    assert names(events) == ["conversation", "status", "status", "token", "token", "citations",
                             "done"]  # fmt: skip
    conversation = events[0][1]
    assert conversation["title"] == FIRST
    tokens = "".join(data["text"] for name, data in events if name == "token")
    done = events[-1][1]
    assert tokens == done["answer"] == "The answer is in the policy [1]."
    [citation] = events[-2][1]
    assert (citation["number"], citation["filename"], citation["text"]) == (1, "leave.txt", LEAVE)
    assert done["conversation_id"] == conversation["id"] and done["not_found"] is False

    [listed] = client.get(f"/api/knowledge-bases/{kb_id}/conversations").json()["items"]
    assert (listed["id"], listed["title"], listed["kb_id"]) == (conversation["id"], FIRST, kb_id)
    detail = client.get(f"/api/conversations/{conversation['id']}").json()
    question, answer = detail["messages"]
    assert (question["role"], question["content"], question["outcome"]) == ("user", FIRST, None)
    assert (answer["role"], answer["outcome"], answer["id"]) == (
        "assistant", "answered", done["message_id"])  # fmt: skip
    assert answer["content"] == done["answer"] and answer["citations"] == events[-2][1]
    assert answer["model"] == "fake-llm-1" and "total" in answer["latency_ms"]


def test_a_follow_up_is_rewritten_with_the_history_and_saved_in_order(client, alice, llm):
    kb_id = library(client, alice, {"leave.txt": LEAVE, "expenses.txt": EXPENSES})
    conversation_id = start(client, kb_id)[0][1]["id"]
    llm.cite = "reimbursed"
    events = follow_up(client, conversation_id)
    assert names(events)[:3] == ["status", "status", "status"]
    assert events[1][1] == {"stage": "retrieving", "query": STANDALONE}

    kind, system, prompt = llm.calls[1]
    assert (kind, system) == ("rewrite", REWRITE_SYSTEM_PROMPT)
    assert f"<user>{FIRST}</user>" in prompt  # the earlier turn, citation markers removed
    assert "<assistant>The answer is in the policy.</assistant>" in prompt
    assert prompt.endswith(f"<question>\n{FOLLOW_UP}\n</question>")
    kind, system, prompt = llm.calls[2]
    assert system == SYSTEM_PROMPT and prompt.endswith(f"<question>\n{STANDALONE}\n</question>")
    assert FIRST not in prompt  # history never reaches the answer prompt (D69)
    [citation] = events[-2][1]
    assert citation["filename"] == "expenses.txt"

    messages = client.get(f"/api/conversations/{conversation_id}").json()["messages"]
    assert [(m["role"], m["content"][:20]) for m in messages] == [
        ("user", FIRST[:20]), ("assistant", "The answer is in the"),
        ("user", FOLLOW_UP[:20]), ("assistant", "The answer is in the"),
    ]  # fmt: skip
    assert messages[2]["rewritten_query"] == STANDALONE and messages[0]["rewritten_query"] is None


def test_nothing_retrieved_is_saved_as_not_found_without_an_llm_call(client, alice, llm):
    act_as(client, alice)
    kb_id = new_kb(client)  # no documents: retrieval finds nothing
    events = start(client, kb_id)
    assert names(events) == ["conversation", "status", "citations", "done"]
    assert events[-1][1]["not_found"] is True and llm.calls == []
    [conversation] = client.get(f"/api/knowledge-bases/{kb_id}/conversations").json()["items"]
    answer = client.get(f"/api/conversations/{conversation['id']}").json()["messages"][1]
    assert (answer["outcome"], answer["content"]) == ("not_found", rag.NOT_FOUND_ANSWER)


def test_a_not_found_answer_sends_and_saves_the_closest_passages(client, alice, llm):
    # M16b, D93: real bge-small scores. The leave passage is close to the question (above the
    # 0.58 floor) but the model finds no answer in it; it's offered as related, not cited.
    kb_id = library(client, alice, {"leave.txt": LEAVE, "expenses.txt": EXPENSES})
    llm.cite = "a phrase in no passage"  # the fake replies NOT_FOUND
    events = start(client, kb_id)
    assert names(events)[-3:] == ["citations", "related", "done"]
    related = dict(events)["related"]
    assert related[0]["filename"] == "leave.txt" and related[0]["number"] == 1
    assert events[-1][1]["related_count"] == len(related) and events[-1][1]["citation_count"] == 0

    conversation_id = events[0][1]["id"]
    answer = client.get(f"/api/conversations/{conversation_id}").json()["messages"][1]
    assert (answer["outcome"], answer["citations"]) == ("not_found", [])
    assert [r["chunk_id"] for r in answer["related"]] == [r["chunk_id"] for r in related]


def test_a_failed_first_answer_leaves_no_conversation(client, alice, llm, db):
    kb_id = library(client, alice, {"leave.txt": LEAVE})
    llm.fail = LLMUnavailableError("The AI service isn't responding right now.")
    events = start(client, kb_id)
    assert names(events)[-1] == "error" and events[-1][1]["code"] == "llm_unavailable"
    assert client.get(f"/api/knowledge-bases/{kb_id}/conversations").json()["items"] == []
    assert db.scalar(select(func.count()).select_from(Conversation)) == 0


def test_rename_and_delete(client, alice, db):
    kb_id = library(client, alice, {"leave.txt": LEAVE})
    conversation_id = start(client, kb_id)[0][1]["id"]
    # Backdated: inside the test's single transaction now() never changes, so an unchanged
    # timestamp would prove nothing otherwise.
    db.execute(update(Conversation).values(updated_at=datetime(2026, 1, 1, tzinfo=UTC)))
    before = client.get(f"/api/conversations/{conversation_id}").json()["updated_at"]
    assert before.startswith("2026-01-01")
    renamed = client.patch(f"/api/conversations/{conversation_id}", json={"title": "  Leave  "})
    assert renamed.status_code == 200 and renamed.json()["title"] == "Leave"
    assert renamed.json()["updated_at"] == before  # renaming isn't activity: the order stays
    assert client.delete(f"/api/conversations/{conversation_id}").status_code == 204
    assert client.get(f"/api/conversations/{conversation_id}").status_code == 404
    assert db.scalar(select(func.count()).select_from(Message)) == 0  # cascade


def test_deleting_the_knowledge_base_deletes_its_conversations(client, alice, db):
    kb_id = library(client, alice, {"leave.txt": LEAVE})
    start(client, kb_id)
    assert client.delete(f"/api/knowledge-bases/{kb_id}").status_code == 204
    assert db.scalar(select(func.count()).select_from(Conversation)) == 0


def test_nobody_sees_or_changes_another_users_conversations(client, alice, bob, llm):
    kb_id = library(client, alice, {"leave.txt": LEAVE})
    conversation_id = start(client, kb_id)[0][1]["id"]
    calls = len(llm.calls)

    act_as(client, bob)
    url = f"/api/conversations/{conversation_id}"
    assert client.get(f"/api/knowledge-bases/{kb_id}/conversations").status_code == 404
    assert client.post(f"/api/knowledge-bases/{kb_id}/conversations",
                       json={"question": FIRST}).status_code == 404  # fmt: skip
    assert client.get(url).status_code == 404
    assert client.patch(url, json={"title": "Mine now"}).status_code == 404
    assert client.post(f"{url}/messages", json={"question": FOLLOW_UP}).status_code == 404
    assert client.delete(url).status_code == 404
    assert len(llm.calls) == calls  # refused before any LLM call

    act_as(client, alice)
    detail = client.get(url).json()
    assert detail["title"] == FIRST and len(detail["messages"]) == 2


def test_the_llm_must_be_configured_before_the_stream_starts(client, alice):
    kb_id = library(client, alice, {"leave.txt": LEAVE})

    def not_configured():
        from app.core.errors import LLMNotConfiguredError

        raise LLMNotConfiguredError("AI answers aren't set up on this server.")

    client.app_.dependency_overrides[get_llm] = not_configured
    response = client.post(f"/api/knowledge-bases/{kb_id}/conversations", json={"question": FIRST})
    assert response.status_code == 503 and response.json()["error"]["code"] == "llm_not_configured"


def test_a_question_can_be_limited_to_one_document(client, alice, llm):
    """M14: with document_id, only that document is searched (its passages are the only
    sources); a document of another knowledge base is a 404 before any LLM call."""
    kb_id = library(client, alice, {"leave.txt": LEAVE, "expenses.txt": EXPENSES})
    by_name = {d["original_filename"]: d["id"] for d in documents(client, kb_id)}
    llm.cite = "reimbursed"
    response = client.post(
        f"/api/knowledge-bases/{kb_id}/conversations",
        json={"question": FIRST, "document_id": by_name["expenses.txt"]},
    )
    events = parse_events(response)
    _, _, prompt = llm.calls[-1]
    assert EXPENSES in prompt and LEAVE not in prompt  # leave.txt wasn't searched
    assert [c["filename"] for c in events[-2][1]] == ["expenses.txt"]

    other_kb = library(client, alice, {"other.txt": "Unrelated text about parking permits."})
    stranger = documents(client, other_kb)[0]["id"]
    calls = len(llm.calls)
    refused = client.post(f"/api/knowledge-bases/{kb_id}/conversations",
                          json={"question": FIRST, "document_id": stranger})  # fmt: skip
    assert refused.status_code == 404
    assert refused.json()["error"]["message"] == "Document not found."
    conversation_id = events[0][1]["id"]
    refused = client.post(f"/api/conversations/{conversation_id}/messages",
                          json={"question": FOLLOW_UP, "document_id": stranger})  # fmt: skip
    assert refused.status_code == 404 and len(llm.calls) == calls


def test_with_multi_query_first_questions_get_one_planning_call(client, alice, llm):
    """M14 (D75): with MULTI_QUERY_ENABLED, every question starts with one planning call (first
    questions too), then the answer. That the phrasings are searched and fused is checked in the
    unit tests (this tiny library returns both documents for any query)."""
    from app.api.deps import get_app_settings

    multi = client.settings_.model_copy(update={"multi_query_enabled": True})
    client.app_.dependency_overrides[get_app_settings] = lambda: multi
    kb_id = library(client, alice, {"leave.txt": LEAVE, "expenses.txt": EXPENSES})
    llm.cite = "reimbursed"
    events = start(client, kb_id, "When do I get my money back for a trip?")
    stages = [d["stage"] for n, d in events if n == "status"]
    assert stages == ["planning", "retrieving", "generating"]
    assert [kind for kind, _, _ in llm.calls] == ["plan", "answer"]
    done = events[-1][1]
    assert done["rewritten_query"] is None and "plan" in done["timings_ms"]  # first: unchanged
    assert [c["filename"] for c in events[-2][1]] == ["expenses.txt"]
