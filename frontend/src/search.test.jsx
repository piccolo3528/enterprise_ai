import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getMe } from "./api/auth";
import { ApiError } from "./api/client";
import { listDocuments } from "./api/documents";
import { listKnowledgeBases } from "./api/knowledgeBases";
import { searchKnowledgeBase } from "./api/search";
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
vi.mock("./api/documents", async (importOriginal) => ({
  ...(await importOriginal()),
  listDocuments: vi.fn(),
}));
vi.mock("./api/search", async (importOriginal) => ({
  ...(await importOriginal()),
  searchKnowledgeBase: vi.fn(),
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

const LEAVE_DOC = {
  id: "d1",
  kb_id: HR.id,
  original_filename: "leave-policy.md",
  status: "ready",
  metadata: { document_id: "NX-HR-002", version: "3.0", status: "current" },
};

function result(overrides = {}) {
  return {
    chunk_id: "c1",
    document_id: "d1",
    filename: "leave-policy.md",
    doc_code: "NX-HR-002",
    doc_version: "3.0",
    doc_status: "current",
    chunk_index: 7,
    section: "6. Carry-Forward › 6.1 Carry-forward",
    page_start: null,
    page_end: null,
    text: "Up to 10 days of unused annual leave can be carried forward.",
    score: 1 / 61 + 1 / 62,
    semantic_rank: 1,
    semantic_score: 0.78,
    keyword_rank: 2,
    keyword_score: 3.6,
    keyword_matched: 3,
    ...overrides,
  };
}

function outcome(mode, results, extra = {}) {
  return { mode, results, query_terms: null, notice: null, timings_ms: { total: 245.1 }, ...extra };
}

beforeEach(() => {
  vi.clearAllMocks();
  getMe.mockResolvedValue(TEST_USER);
  listKnowledgeBases.mockResolvedValue([kb(HR), kb(FIN)]);
  listDocuments.mockResolvedValue([LEAVE_DOC, { ...LEAVE_DOC, id: "d2", status: "failed" }]);
  searchKnowledgeBase.mockImplementation(async (_kb, { mode }) => outcome(mode, [result()]));
});

async function searchFor(text) {
  const user = userEvent.setup();
  const box = await screen.findByRole("searchbox", { name: "Search for" });
  await user.clear(box);
  await user.type(box, text);
  await user.click(screen.getByRole("button", { name: "Search" }));
  return user;
}

describe("search page", () => {
  it("is in the sidebar now", async () => {
    renderApp("/search");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Search" })).toHaveAttribute("href", "/search");
  });

  it("searches the first knowledge base in hybrid mode and shows a result card", async () => {
    renderApp("/search");
    await searchFor("carry forward leave");

    await waitFor(() =>
      expect(searchKnowledgeBase).toHaveBeenCalledWith(
        HR.id,
        { query: "carry forward leave", mode: "hybrid", documentId: undefined },
        expect.anything(),
      ),
    );
    const results = await screen.findByRole("region", { name: "Results" });
    expect(results).toHaveTextContent("1 passage · hybrid · 245 ms on the server");
    expect(within(results).getByRole("link", { name: "NX-HR-002 v3.0" })).toHaveAttribute(
      "href",
      `/knowledge-bases/${HR.id}/documents/d1`,
    );
    expect(results).toHaveTextContent("6. Carry-Forward › 6.1 Carry-forward");
    expect(results).toHaveTextContent("Fused score 0.0325 · semantic #1 · keyword #2");
    expect(results).toHaveTextContent("Up to 10 days of unused annual leave");
  });

  it("re-runs the search when the mode changes, and explains each mode's score", async () => {
    renderApp("/search?q=carry%20forward");
    const user = userEvent.setup();
    expect(await screen.findByText(/semantic #1/)).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "Semantic" }));
    await waitFor(() =>
      expect(searchKnowledgeBase).toHaveBeenLastCalledWith(
        HR.id,
        expect.objectContaining({ mode: "semantic" }),
        expect.anything(),
      ),
    );
    expect(await screen.findByText("Similarity 0.033")).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "Keyword" }));
    expect(await screen.findByText("3 words matched")).toBeInTheDocument();
  });

  it("offers only ready documents in the filter and passes the chosen one", async () => {
    renderApp("/search?q=leave");
    const user = userEvent.setup();
    const filter = await screen.findByRole("combobox", { name: "Document" });
    await waitFor(() => expect(within(filter).getAllByRole("option")).toHaveLength(2));
    expect(within(filter).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "All documents",
      "NX-HR-002 v3.0 · leave-policy.md",
    ]);

    await user.selectOptions(filter, "d1");
    await waitFor(() =>
      expect(searchKnowledgeBase).toHaveBeenLastCalledWith(
        HR.id,
        expect.objectContaining({ documentId: "d1" }),
        expect.anything(),
      ),
    );
  });

  it("switches knowledge base from the select, or from the ?kb= link", async () => {
    renderApp(`/search?kb=${FIN.id}&q=leave`);
    const user = userEvent.setup();
    await waitFor(() =>
      expect(searchKnowledgeBase).toHaveBeenCalledWith(FIN.id, expect.anything(), expect.anything()),
    );
    await user.selectOptions(screen.getByRole("combobox", { name: "Knowledge base" }), HR.id);
    await waitFor(() =>
      expect(searchKnowledgeBase).toHaveBeenLastCalledWith(HR.id, expect.anything(), expect.anything()),
    );
  });

  it("marks passages from documents that aren't current", async () => {
    searchKnowledgeBase.mockResolvedValue(
      outcome("hybrid", [result({ doc_version: "2.0", doc_status: "archived" })]),
    );
    renderApp("/search?q=leave");
    const results = await screen.findByRole("region", { name: "Results" });
    expect(within(results).getByText("archived")).toBeInTheDocument();
  });

  it("asks for a query instead of sending an empty one", async () => {
    renderApp("/search");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Search" }));
    expect(screen.getByText("Enter something to search for.")).toBeInTheDocument();
    expect(searchKnowledgeBase).not.toHaveBeenCalled();
  });

  it("says when nothing matched, with a hint for the mode", async () => {
    searchKnowledgeBase.mockResolvedValue(outcome("keyword", []));
    renderApp("/search?q=overseas&mode=keyword");
    expect(await screen.findByRole("heading", { name: "No matching passages" })).toBeInTheDocument();
    expect(screen.getByText(/Try semantic or hybrid/)).toBeInTheDocument();
  });

  it("shows the server's notice, e.g. hybrid falling back to keyword", async () => {
    searchKnowledgeBase.mockResolvedValue(
      outcome("hybrid", [result({ semantic_rank: null })], {
        notice: "Semantic search is unavailable right now, so these are keyword matches only.",
      }),
    );
    renderApp("/search?q=leave");
    expect(await screen.findByText(/keyword matches only/)).toHaveAttribute("role", "status");
    expect(screen.getByText(/not in semantic · keyword #2/)).toBeInTheDocument();
  });

  it("shows a failed search with its reference and a retry", async () => {
    searchKnowledgeBase.mockRejectedValueOnce(
      new ApiError({ status: 503, code: "service_unavailable", message: "Semantic search is unavailable right now.", requestId: "req-42" }),
    );
    renderApp("/search?q=leave&mode=semantic");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Semantic search is unavailable right now.");
    expect(alert).toHaveTextContent("req-42");
    await userEvent.setup().click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("region", { name: "Results" })).toBeInTheDocument();
  });

  it("points to the knowledge bases page when there is nothing to search", async () => {
    listKnowledgeBases.mockResolvedValue([]);
    renderApp("/search");
    expect(await screen.findByRole("heading", { name: "Nothing to search yet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to knowledge bases" })).toBeInTheDocument();
  });
});

describe("search page, empty results with a notice", () => {
  it("shows the server's explanation instead of a generic hint", async () => {
    searchKnowledgeBase.mockResolvedValue(
      outcome("keyword", [], { query_terms: 0, notice: "Keyword search ignores very common words." }),
    );
    renderApp("/search?q=what%20is%20the&mode=keyword");
    expect(await screen.findByText("Keyword search ignores very common words.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "No matching passages" })).toBeInTheDocument();
    expect(screen.queryByText(/Try semantic or hybrid/)).not.toBeInTheDocument();
  });
});
