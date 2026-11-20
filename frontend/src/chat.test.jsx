import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getMe } from "./api/auth";
import { ApiError } from "./api/client";
import {
  deleteConversation,
  getConversation,
  listConversations,
  renameConversation,
  streamAnswer,
} from "./api/conversations";
import { listDocuments } from "./api/documents";
import { listKnowledgeBases } from "./api/knowledgeBases";
import { linkCitations } from "./components/chat/AnswerText";
import { renderApp, TEST_USER } from "./test/renderApp";

vi.mock("./api/health", () => ({ getHealth: vi.fn(() => new Promise(() => {})) }));
vi.mock("./api/auth", () => ({ getMe: vi.fn(), login: vi.fn(), register: vi.fn(), logout: vi.fn() }));
vi.mock("./api/knowledgeBases", () => ({
  listKnowledgeBases: vi.fn(),
  getKnowledgeBase: vi.fn(),
  createKnowledgeBase: vi.fn(),
  updateKnowledgeBase: vi.fn(),
  deleteKnowledgeBase: vi.fn(),
}));
vi.mock("./api/documents", () => ({ listDocuments: vi.fn() }));
vi.mock("./api/conversations", async (importOriginal) => ({
  ...(await importOriginal()),
  listConversations: vi.fn(),
  getConversation: vi.fn(),
  renameConversation: vi.fn(),
  deleteConversation: vi.fn(),
  streamAnswer: vi.fn(),
}));

const HR = { id: "11111111-1111-4111-8111-111111111111", name: "HR Policies" };
const FIN = { id: "22222222-2222-4222-8222-222222222222", name: "Finance" };
const kb = (base) => ({
  description: null,
  document_count: 1,
  conversation_count: 0,
  created_at: "2026-11-09T10:00:00Z",
  updated_at: "2026-11-09T10:00:00Z",
  ...base,
});
const conversation = (id, title) => ({
  id,
  kb_id: HR.id,
  title,
  created_at: "2026-11-19T10:00:00Z",
  updated_at: "2026-11-19T10:00:00Z",
});
const NEW = conversation("33333333-3333-4333-8333-333333333333", "How much leave can I carry forward?");
const SAVED = conversation("44444444-4444-4444-8444-444444444444", "Expense claims");

function citation(number, overrides = {}) {
  return {
    number,
    chunk_id: `c${number}`,
    document_id: `d${number}`,
    filename: `policy-${number}.md`,
    doc_code: "NX-HR-002",
    doc_version: "3.0",
    doc_status: "current",
    doc_title: "Annual Leave Policy",
    section: "6. Carry-Forward",
    page_start: null,
    page_end: null,
    text: `Passage ${number}: up to 10 days can be carried forward.`,
    flagged: false,
    ...overrides,
  };
}

const ANSWER = "You can carry forward **up to 10 days** [1], approved by your manager [2].";
const CITATIONS = [citation(1), citation(2, { doc_version: "2.0", doc_status: "superseded" })];

/** The events of one streamed answer, as streamAnswer hands them to the page. */
function events({
  answer = ANSWER,
  citations = CITATIONS,
  notFound = false,
  notices = [],
  rewritten = null,
  isNew = true,
} = {}) {
  return [
    ...(isNew ? [["conversation", { id: NEW.id, title: NEW.title }]] : []),
    ...(rewritten ? [["status", { stage: "rewriting" }]] : []),
    ["status", { stage: "retrieving", query: rewritten }],
    ["status", { stage: "generating" }],
    ...(notFound ? [] : [["token", { text: answer.slice(0, 25) }], ["token", { text: answer.slice(25) }]]),
    ["citations", notFound ? [] : citations],
    [
      "done",
      {
        message_id: "m1",
        conversation_id: NEW.id,
        answer,
        not_found: notFound,
        notices,
        model: "gemini-3.5-flash-lite",
        sources_given: 8,
        rewritten_query: rewritten,
        citation_count: notFound ? 0 : citations.length,
        timings_ms: { total: 3456 },
      },
    ],
  ];
}

/** A streamAnswer stand-in that plays `script`, one event per microtask. */
function plays(script) {
  return async ({ onEvent }) => {
    for (const [name, data] of script) {
      await Promise.resolve();
      onEvent(name, data);
    }
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  getMe.mockResolvedValue(TEST_USER);
  listKnowledgeBases.mockResolvedValue([kb(HR), kb(FIN)]);
  listConversations.mockResolvedValue([]);
  listDocuments.mockResolvedValue([]);
  streamAnswer.mockImplementation(plays(events()));
});

async function ask(text, user = userEvent.setup()) {
  const box = await screen.findByRole("textbox", { name: /Your (follow-up )?question/ });
  await user.type(box, text);
  await user.click(screen.getByRole("button", { name: "Ask" }));
  return user;
}

describe("chat page", () => {
  it("is in the sidebar and linked from a knowledge base's KB select", async () => {
    renderApp(`/chat?kb=${FIN.id}`);
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Chat" })).toHaveAttribute("href", "/chat");
    expect(await screen.findByRole("combobox", { name: "Knowledge base" })).toHaveValue(FIN.id);
    expect(screen.getByText(/sent to Google Gemini on its free tier/)).toBeInTheDocument();
    await waitFor(() => expect(listConversations).toHaveBeenCalledWith(FIN.id, expect.anything()));
  });

  it("streams the answer, then shows citation chips, the meta line and the sources", async () => {
    listConversations.mockResolvedValueOnce([]).mockResolvedValue([NEW]);
    renderApp("/chat");
    await ask("How much leave can I carry forward?");

    expect(streamAnswer).toHaveBeenCalledWith(
      expect.objectContaining({ kbId: HR.id, conversationId: null, question: "How much leave can I carry forward?" }),
    );
    const article = await screen.findByRole("article", { name: "Answer" });
    await waitFor(() => expect(within(article).getByRole("button", { name: "Show source 1" })).toBeInTheDocument());
    expect(within(article).getByText("up to 10 days").tagName).toBe("STRONG"); // Markdown
    expect(screen.getByText(/gemini-3.5-flash-lite · 3.5 s · 8 passages given · 2 sources cited/)).toBeInTheDocument();

    const panel = screen.getByRole("complementary", { name: "Sources" });
    expect(panel).toHaveTextContent("Passage 1: up to 10 days");
    expect(panel).toHaveTextContent("superseded");
    expect(within(panel).getByRole("link", { name: "Open document" })).toHaveAttribute(
      "href",
      `/knowledge-bases/${HR.id}/documents/d1`,
    );
    // The new conversation is listed and marked as the open one.
    const list = screen.getByRole("navigation", { name: "Conversations" });
    expect(await within(list).findByRole("button", { name: NEW.title })).toHaveAttribute("aria-current", "page");
  });

  it("shows the text while it streams, with plain numbers until the sources arrive, and can stop", async () => {
    let release;
    streamAnswer.mockImplementation(async ({ onEvent, signal }) => {
      onEvent("conversation", { id: NEW.id, title: NEW.title });
      onEvent("status", { stage: "retrieving", query: null });
      await new Promise((resolve) => {
        release = resolve;
      });
      onEvent("status", { stage: "generating" });
      onEvent("token", { text: "You can carry forward up to 10 days [1]" });
      await new Promise((_, reject) =>
        signal.addEventListener("abort", () => reject(new ApiError({ code: "aborted", message: "x" }))),
      );
    });
    renderApp("/chat");
    const user = await ask("Carry forward?");

    expect(await screen.findByText("Searching your documents…")).toBeInTheDocument();
    release();
    const article = await screen.findByRole("article", { name: "Answer" });
    expect(article).toHaveTextContent("You can carry forward up to 10 days 1");
    expect(within(article).queryByRole("button")).not.toBeInTheDocument(); // not clickable yet
    expect(screen.queryByRole("button", { name: "Ask" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Stop" }));
    expect(await screen.findByText("Stopped. The part shown is kept in this conversation.")).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Answer" })).toHaveTextContent("up to 10 days");
    expect(screen.getByRole("button", { name: "Ask" })).toBeInTheDocument();
  });

  it("sends a follow-up to the same conversation and shows what was searched", async () => {
    renderApp("/chat");
    const user = await ask("How much leave can I carry forward?");
    await screen.findByText(/2 sources cited/);

    streamAnswer.mockImplementation(
      plays(events({ isNew: false, rewritten: "Can unused annual leave be carried into next year?" })),
    );
    await ask("Can they be carried into next year?", user);
    await waitFor(() => expect(streamAnswer).toHaveBeenCalledTimes(2));
    expect(streamAnswer.mock.calls[1][0]).toMatchObject({
      kbId: HR.id,
      conversationId: NEW.id,
      question: "Can they be carried into next year?",
    });
    expect(await screen.findByText("Can unused annual leave be carried into next year?")).toBeInTheDocument();
    expect(screen.getByText(/Searched for:/)).toBeInTheDocument();
    expect(screen.getAllByRole("article", { name: "Answer" })).toHaveLength(2);
  });

  it("opens a saved conversation with its answers and sources", async () => {
    listConversations.mockResolvedValue([SAVED]);
    const message = (fields) => ({
      rewritten_query: null,
      outcome: null,
      citations: [],
      notices: [],
      model: null,
      latency_ms: {},
      created_at: "2026-11-19T10:00:00Z",
      ...fields,
    });
    getConversation.mockResolvedValue({
      ...SAVED,
      messages: [
        message({ id: "u1", role: "user", content: "How are expenses paid?" }),
        message({
          id: "a1",
          role: "assistant",
          content: "Within 14 days [1].",
          outcome: "answered",
          citations: [citation(1, { text: "Expenses are reimbursed within 14 days." })],
          model: "gemini-3.5-flash-lite",
          latency_ms: { total: 2100 },
        }),
      ],
    });
    renderApp("/chat");
    const list = await screen.findByRole("navigation", { name: "Conversations" });
    await userEvent.click(await within(list).findByRole("button", { name: "Expense claims" }));

    expect(getConversation).toHaveBeenCalledWith(SAVED.id, expect.anything());
    expect(await screen.findByText("How are expenses paid?")).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Answer" })).toHaveTextContent("Within 14 days");
    expect(screen.getByRole("complementary", { name: "Sources" })).toHaveTextContent("reimbursed within 14 days");
    expect(screen.getByRole("textbox", { name: "Your follow-up question" })).toBeInTheDocument();
  });

  it("renames a conversation in place", async () => {
    listConversations.mockResolvedValue([SAVED]);
    renameConversation.mockResolvedValue({ ...SAVED, title: "Travel expenses" });
    renderApp("/chat");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: 'Rename "Expense claims"' }));
    const field = screen.getByRole("textbox", { name: "Conversation title" });
    await user.clear(field);
    await user.type(field, "Travel expenses{Enter}");

    expect(renameConversation).toHaveBeenCalledWith(SAVED.id, "Travel expenses");
    expect(await screen.findByRole("button", { name: "Travel expenses" })).toBeInTheDocument();
  });

  it("deletes a conversation after confirming and goes back to a new chat", async () => {
    listConversations.mockResolvedValue([SAVED]);
    getConversation.mockResolvedValue({ ...SAVED, messages: [] });
    deleteConversation.mockResolvedValue();
    renderApp(`/chat?kb=${HR.id}&c=${SAVED.id}`);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: 'Delete "Expense claims"' }));
    const dialog = screen.getByRole("dialog", { name: "Delete this conversation?" });
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    expect(deleteConversation).toHaveBeenCalledWith(SAVED.id);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Expense claims" })).not.toBeInTheDocument();
    expect(screen.getByText("Ask about your documents")).toBeInTheDocument();
  });

  it("shows a not-found answer without sources", async () => {
    streamAnswer.mockImplementation(
      plays(events({ notFound: true, answer: "I couldn't find the answer to that in this knowledge base's documents." })),
    );
    renderApp("/chat");
    await ask("Can I bring my dog?");
    expect(await screen.findByText(/couldn't find the answer/)).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: "Answer" })).not.toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Sources" })).toHaveTextContent(
      "The sources an answer cites appear here",
    );
  });

  it("shows notices and warns about a flagged source", async () => {
    streamAnswer.mockImplementation(
      plays(
        events({
          answer: "It says yes [1].",
          citations: [citation(1, { flagged: true })],
          notices: ["A cited passage contains text that looks like instructions to an AI."],
        }),
      ),
    );
    renderApp("/chat");
    await ask("Is it approved?");
    expect(await screen.findByText(/looks like instructions to an AI\.$/)).toBeInTheDocument();
    const panel = screen.getByRole("complementary", { name: "Sources" });
    expect(panel).toHaveTextContent("Suspicious text");
    expect(panel).toHaveTextContent("It was treated as document content only.");
  });

  it("never renders raw HTML from an answer", async () => {
    streamAnswer.mockImplementation(
      plays(events({ answer: 'Hello <img src="x" onerror="alert(1)"> <script>alert(2)</script> [1]' })),
    );
    const { container } = renderApp("/chat");
    await ask("Test?");
    await screen.findByText(/2 sources cited|1 source cited/);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("article script")).toBeNull();
  });

  it("shows the error with a retry that asks again", async () => {
    streamAnswer.mockRejectedValueOnce(
      new ApiError({ code: "rate_limited", message: "Too many questions in a short time." }),
    );
    renderApp("/chat");
    const user = await ask("Carry forward?");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't answer this question");
    expect(alert).toHaveTextContent("Too many questions in a short time.");

    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("article", { name: "Answer" })).toBeInTheDocument();
    expect(streamAnswer).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });

  it("forgets a new conversation whose first answer failed (it wasn't saved)", async () => {
    // Found in M13's Chrome check: Gemini returned 503 mid-answer; the URL kept the unsaved id.
    streamAnswer.mockImplementationOnce(async ({ onEvent }) => {
      onEvent("conversation", { id: NEW.id, title: NEW.title });
      onEvent("token", { text: "Employees get 20 days" });
      throw new ApiError({ code: "llm_unavailable", message: "The AI service isn't responding right now." });
    });
    renderApp("/chat");
    const user = await ask("How many days of leave?");
    const alert = await screen.findByRole("alert");
    expect(screen.queryByRole("article", { name: "Answer" })).not.toBeInTheDocument(); // partial dropped

    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    await screen.findByText(/2 sources cited/);
    expect(streamAnswer.mock.calls[1][0]).toMatchObject({ conversationId: null, kbId: HR.id });
    expect(getConversation).not.toHaveBeenCalled();
  });

  it("can limit the search to one ready document and says so under the question", async () => {
    const doc = (id, status, metadata) => ({ id, status, original_filename: `${id}.md`, metadata });
    listDocuments.mockResolvedValue([
      doc("leave", "ready", { document_id: "NX-HR-002", version: "3.0", title: "Annual Leave" }),
      doc("notes", "ready", {}),
      doc("pending", "processing", {}),
    ]);
    renderApp("/chat");
    const user = userEvent.setup();
    const scope = await screen.findByRole("combobox", { name: "Search in" });
    await waitFor(() => expect(within(scope).getAllByRole("option")).toHaveLength(3)); // all + 2 ready
    expect(within(scope).getByRole("option", { name: "NX-HR-002 v3.0 · Annual Leave" })).toBeInTheDocument();
    expect(within(scope).getByRole("option", { name: "notes.md" })).toBeInTheDocument();

    await user.selectOptions(scope, "leave");
    await ask("Carry forward?", user);
    expect(streamAnswer).toHaveBeenCalledWith(expect.objectContaining({ documentId: "leave" }));
    const note = await screen.findByText(/Searched in:/);
    expect(note).toHaveTextContent("Searched in: NX-HR-002 v3.0 · Annual Leave only");
  });

  it("needs a question, sends on Enter and keeps Shift+Enter for new lines", async () => {
    renderApp("/chat");
    const user = userEvent.setup();
    const box = await screen.findByRole("textbox", { name: "Your question" });
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(screen.getByText("Ask a question first.")).toBeInTheDocument();
    expect(streamAnswer).not.toHaveBeenCalled();

    await user.type(box, "Line one{Shift>}{Enter}{/Shift}line two");
    expect(box).toHaveValue("Line one\nline two");
    await user.type(box, "{Enter}");
    await waitFor(() =>
      expect(streamAnswer).toHaveBeenCalledWith(expect.objectContaining({ question: "Line one\nline two" })),
    );
    expect(box).toHaveValue("");
  });

  it("starts afresh when another knowledge base is selected", async () => {
    renderApp("/chat");
    const user = await ask("Carry forward?");
    await screen.findByText(/2 sources cited/);
    await user.selectOptions(screen.getByRole("combobox", { name: "Knowledge base" }), FIN.id);
    await waitFor(() => expect(screen.queryByRole("article", { name: "Answer" })).not.toBeInTheDocument());
    expect(screen.getByText("Ask about your documents")).toBeInTheDocument();
  });

  it("links citation markers but not real links or other brackets", () => {
    expect(linkCitations("A [1][2]. See [the form](https://x.example). [Note]")).toBe(
      "A [1](#cite-1)[2](#cite-2). See [the form](https://x.example). [Note]",
    );
  });
});
