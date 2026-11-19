import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { askKnowledgeBase } from "./api/answers";
import { getMe } from "./api/auth";
import { ApiError } from "./api/client";
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
vi.mock("./api/answers", async (importOriginal) => ({
  ...(await importOriginal()),
  askKnowledgeBase: vi.fn(),
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

function answer(overrides = {}) {
  return {
    answer: "You can carry forward **up to 10 days** [1], approved by your manager [2].",
    not_found: false,
    citations: [citation(1), citation(2, { doc_version: "2.0", doc_status: "superseded" })],
    notices: [],
    model: "gemini-3.5-flash-lite",
    prompt_tokens: 1800,
    output_tokens: 40,
    sources_given: 8,
    invalid_citations: 0,
    prompt_version: "answer-v1",
    timings_ms: { total: 3456 },
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  getMe.mockResolvedValue(TEST_USER);
  listKnowledgeBases.mockResolvedValue([kb(HR), kb(FIN)]);
  askKnowledgeBase.mockResolvedValue(answer());
});

async function ask(text) {
  const user = userEvent.setup();
  const box = await screen.findByRole("textbox", { name: "Your question" });
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
  });

  it("asks the selected knowledge base and renders the answer with citation chips", async () => {
    renderApp("/chat");
    await ask("How much leave can I carry forward?");

    expect(askKnowledgeBase).toHaveBeenCalledWith(
      HR.id,
      "How much leave can I carry forward?",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    const article = await screen.findByRole("article", { name: "Answer" });
    expect(within(article).getByText("up to 10 days").tagName).toBe("STRONG"); // Markdown
    expect(within(article).getByRole("button", { name: "Show source 1" })).toBeInTheDocument();
    expect(screen.getByText(/gemini-3.5-flash-lite · 3.5 s · 8 passages given · 2 sources cited/))
      .toBeInTheDocument();

    // The first source is open in the panel; the second shows its outdated status.
    const panel = screen.getByRole("complementary", { name: "Sources" });
    expect(panel).toHaveTextContent("Passage 1: up to 10 days");
    expect(panel).toHaveTextContent("superseded");
    expect(within(panel).getByRole("link", { name: "Open document" })).toHaveAttribute(
      "href",
      `/knowledge-bases/${HR.id}/documents/d1`,
    );
  });

  it("opens the passage of the citation that was clicked", async () => {
    renderApp("/chat");
    const user = await ask("Carry forward?");
    const article = await screen.findByRole("article", { name: "Answer" });
    await user.click(within(article).getByRole("button", { name: "Show source 2" }));

    const panel = screen.getByRole("complementary", { name: "Sources" });
    expect(panel).toHaveTextContent("Passage 2");
    expect(panel).not.toHaveTextContent("Passage 1");
    expect(within(article).getByRole("button", { name: "Show source 2" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("shows a not-found answer without sources", async () => {
    askKnowledgeBase.mockResolvedValue(
      answer({
        answer: "I couldn't find the answer to that in this knowledge base's documents.",
        not_found: true,
        citations: [],
      }),
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
    askKnowledgeBase.mockResolvedValue(
      answer({
        answer: "It says yes [1].",
        citations: [citation(1, { flagged: true })],
        notices: ["A cited passage contains text that looks like instructions to an AI."],
      }),
    );
    renderApp("/chat");
    await ask("Is it approved?");
    expect(await screen.findByText(/looks like instructions to an AI\.$/)).toBeInTheDocument();
    const panel = screen.getByRole("complementary", { name: "Sources" });
    expect(panel).toHaveTextContent("Suspicious text");
    expect(panel).toHaveTextContent("It was treated as document content only.");
  });

  it("never renders raw HTML from an answer", async () => {
    askKnowledgeBase.mockResolvedValue(
      answer({ answer: 'Hello <img src="x" onerror="alert(1)"> <script>alert(2)</script> [1]' }),
    );
    const { container } = renderApp("/chat");
    await ask("Test?");
    await screen.findByRole("article", { name: "Answer" });
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("article script")).toBeNull();
  });

  it("shows the error with a retry that asks again", async () => {
    askKnowledgeBase.mockRejectedValueOnce(
      new ApiError({ status: 429, code: "rate_limited", message: "Too many questions in a short time." }),
    );
    renderApp("/chat");
    const user = await ask("Carry forward?");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't answer this question");
    expect(alert).toHaveTextContent("Too many questions in a short time.");

    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("article", { name: "Answer" })).toBeInTheDocument();
    expect(askKnowledgeBase).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("needs a question, sends on Enter and keeps Shift+Enter for new lines", async () => {
    renderApp("/chat");
    const user = userEvent.setup();
    const box = await screen.findByRole("textbox", { name: "Your question" });
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(screen.getByText("Ask a question first.")).toBeInTheDocument();
    expect(askKnowledgeBase).not.toHaveBeenCalled();

    await user.type(box, "Line one{Shift>}{Enter}{/Shift}line two");
    expect(box).toHaveValue("Line one\nline two");
    await user.type(box, "{Enter}");
    await waitFor(() =>
      expect(askKnowledgeBase).toHaveBeenCalledWith(HR.id, "Line one\nline two", expect.anything()),
    );
    expect(box).toHaveValue("");
  });

  it("starts afresh when another knowledge base is selected", async () => {
    renderApp("/chat");
    const user = await ask("Carry forward?");
    await screen.findByRole("article", { name: "Answer" });
    await user.selectOptions(screen.getByRole("combobox", { name: "Knowledge base" }), FIN.id);
    await waitFor(() =>
      expect(screen.queryByRole("article", { name: "Answer" })).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Ask about your documents")).toBeInTheDocument();
  });

  it("links citation markers but not real links or other brackets", () => {
    expect(linkCitations("A [1][2]. See [the form](https://x.example). [Note]")).toBe(
      "A [1](#cite-1)[2](#cite-2). See [the form](https://x.example). [Note]",
    );
  });
});
