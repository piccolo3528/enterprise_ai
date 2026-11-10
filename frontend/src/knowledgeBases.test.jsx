import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getMe } from "./api/auth";
import { ApiError } from "./api/client";
import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  getKnowledgeBase,
  listKnowledgeBases,
  updateKnowledgeBase,
} from "./api/knowledgeBases";
import { listDocuments } from "./api/documents";
import { renderApp, TEST_USER } from "./test/renderApp";

vi.mock("./api/health", () => ({ getHealth: vi.fn(() => new Promise(() => {})) }));
vi.mock("./api/auth", () => ({ getMe: vi.fn(), login: vi.fn(), register: vi.fn(), logout: vi.fn() }));
vi.mock("./api/documents", async (importOriginal) => ({
  ...(await importOriginal()),
  listDocuments: vi.fn(),
}));
vi.mock("./api/knowledgeBases", () => ({
  listKnowledgeBases: vi.fn(),
  getKnowledgeBase: vi.fn(),
  createKnowledgeBase: vi.fn(),
  updateKnowledgeBase: vi.fn(),
  deleteKnowledgeBase: vi.fn(),
}));

function kb(overrides = {}) {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    name: "HR Policies",
    description: "Leave, travel and benefits",
    document_count: 0,
    conversation_count: 0,
    created_at: "2026-11-09T10:00:00Z",
    updated_at: "2026-11-09T10:00:00Z",
    ...overrides,
  };
}

const HR = kb();
const IT = kb({
  id: "22222222-2222-4222-8222-222222222222",
  name: "IT Procedures",
  description: null,
  document_count: 3,
  conversation_count: 2,
  updated_at: "2026-11-08T10:00:00Z",
});

const notFound = () =>
  new ApiError({ status: 404, code: "not_found", message: "Knowledge base not found." });

beforeEach(() => {
  vi.clearAllMocks();
  getMe.mockResolvedValue(TEST_USER);
  listKnowledgeBases.mockResolvedValue([HR, IT]);
  listDocuments.mockResolvedValue([]);
});

describe("knowledge base list", () => {
  it("shows each knowledge base with its counts, linking to its page", async () => {
    renderApp("/knowledge-bases");
    const link = await screen.findByRole("link", { name: "IT Procedures" });
    expect(link).toHaveAttribute("href", `/knowledge-bases/${IT.id}`);
    const card = link.closest("li");
    expect(card).toHaveTextContent("3 documents");
    expect(card).toHaveTextContent("2 conversations");
    expect(card).toHaveTextContent("No description");
    expect(screen.getByRole("link", { name: "HR Policies" }).closest("li")).toHaveTextContent(
      "0 documents",
    );
  });

  it("invites the user to create one when there are none", async () => {
    listKnowledgeBases.mockResolvedValue([]);
    renderApp("/knowledge-bases");
    expect(await screen.findByRole("heading", { name: "No knowledge bases yet" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "New knowledge base" }));
    expect(screen.getByRole("dialog", { name: "New knowledge base" })).toBeInTheDocument();
  });

  it("shows a load failure with its reference, and retries", async () => {
    listKnowledgeBases.mockRejectedValueOnce(
      new ApiError({ status: 500, code: "internal_error", message: "Boom.", requestId: "abc123" }),
    );
    renderApp("/knowledge-bases");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Reference: abc123");
    await userEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: "HR Policies" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("creating", () => {
  it("creates a knowledge base and opens its page", async () => {
    const created = kb({ id: "33333333-3333-4333-8333-333333333333", name: "Finance" });
    createKnowledgeBase.mockResolvedValue(created);
    getKnowledgeBase.mockResolvedValue(created);
    renderApp("/knowledge-bases");

    await userEvent.click(await screen.findByRole("button", { name: "New knowledge base" }));
    const dialog = screen.getByRole("dialog", { name: "New knowledge base" });
    const name = within(dialog).getByLabelText("Name");
    expect(name).toHaveFocus(); // focus moves into the dialog
    await userEvent.type(name, "Finance");
    await userEvent.type(within(dialog).getByLabelText("Description (optional)"), "Budgets");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create" }));

    expect(createKnowledgeBase).toHaveBeenCalledWith({ name: "Finance", description: "Budgets" });
    expect(await screen.findByRole("heading", { name: "Finance", level: 1 })).toBeInTheDocument();
    expect(getKnowledgeBase).toHaveBeenCalledWith(created.id, expect.anything());
  });

  it("shows a taken name next to the field and keeps the dialog open", async () => {
    createKnowledgeBase.mockRejectedValue(
      new ApiError({
        status: 409,
        code: "conflict",
        message: 'You already have a knowledge base called "hr policies".',
      }),
    );
    renderApp("/knowledge-bases");
    await userEvent.click(await screen.findByRole("button", { name: "New knowledge base" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Name"), "hr policies");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create" }));

    expect(await within(dialog).findByText(/already have a knowledge base/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Name")).toHaveAttribute("aria-invalid", "true");
  });

  it("doesn't send a blank name", async () => {
    renderApp("/knowledge-bases");
    await userEvent.click(await screen.findByRole("button", { name: "New knowledge base" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Name"), "   ");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create" }));
    expect(within(dialog).getByText("Enter a name")).toBeInTheDocument();
    expect(createKnowledgeBase).not.toHaveBeenCalled();
  });

  it("closes with Escape without saving, and returns focus to the button", async () => {
    renderApp("/knowledge-bases");
    const open = await screen.findByRole("button", { name: "New knowledge base" });
    await userEvent.click(open);
    await userEvent.type(screen.getByLabelText("Name"), "Draft");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(open).toHaveFocus();

    await userEvent.click(open); // a fresh form each time
    expect(screen.getByLabelText("Name")).toHaveValue("");
    expect(createKnowledgeBase).not.toHaveBeenCalled();
  });
});

describe("editing and deleting from the list", () => {
  it("renames a knowledge base in place", async () => {
    updateKnowledgeBase.mockResolvedValue({
      ...IT,
      name: "IT Runbooks",
      updated_at: "2026-11-10T09:00:00Z",
    });
    renderApp("/knowledge-bases");
    await userEvent.click(await screen.findByRole("button", { name: "Edit IT Procedures" }));
    const dialog = screen.getByRole("dialog", { name: "Edit knowledge base" });
    const name = within(dialog).getByLabelText("Name");
    expect(name).toHaveValue("IT Procedures");
    await userEvent.clear(name);
    await userEvent.type(name, "IT Runbooks");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));

    expect(updateKnowledgeBase).toHaveBeenCalledWith(IT.id, { name: "IT Runbooks", description: "" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const names = screen.getAllByRole("listitem").map((li) => within(li).getByRole("link").textContent);
    expect(names).toEqual(["IT Runbooks", "HR Policies"]); // most recently changed first
  });

  it("asks before deleting, then removes the card", async () => {
    deleteKnowledgeBase.mockResolvedValue();
    renderApp("/knowledge-bases");
    await userEvent.click(await screen.findByRole("button", { name: "Delete IT Procedures" }));
    const dialog = screen.getByRole("dialog", { name: 'Delete "IT Procedures"?' });
    expect(dialog).toHaveTextContent("its 3 documents and 2 conversations");
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus(); // safe default
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete" }));

    expect(deleteKnowledgeBase).toHaveBeenCalledWith(IT.id);
    expect(await screen.findByRole("status")).toHaveTextContent('Deleted "IT Procedures".');
    expect(screen.queryByRole("link", { name: "IT Procedures" })).not.toBeInTheDocument();
  });

  it("treats an already-deleted knowledge base as deleted", async () => {
    deleteKnowledgeBase.mockRejectedValue(notFound());
    renderApp("/knowledge-bases");
    await userEvent.click(await screen.findByRole("button", { name: "Delete HR Policies" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(await screen.findByRole("status")).toHaveTextContent('Deleted "HR Policies".');
  });

  it("keeps the dialog open with the error when deleting fails", async () => {
    deleteKnowledgeBase.mockRejectedValue(
      new ApiError({ status: 503, code: "backend_unreachable", message: "Can't reach the backend." }),
    );
    renderApp("/knowledge-bases");
    await userEvent.click(await screen.findByRole("button", { name: "Delete HR Policies" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Can't reach the backend.");
    expect(screen.getByRole("link", { name: "HR Policies" })).toBeInTheDocument();
  });
});

describe("knowledge base page", () => {
  it("shows the details and counts", async () => {
    getKnowledgeBase.mockResolvedValue(IT);
    listDocuments.mockResolvedValue(
      ["a", "b", "c"].map((n) => ({
        id: n,
        kb_id: IT.id,
        original_filename: `${n}.md`,
        file_type: "md",
        size_bytes: 10,
        status: "ready",
        error_message: null,
        page_count: null,
        chunk_count: 0,
        metadata: {},
        created_at: "2026-11-09T10:00:00Z",
        processed_at: "2026-11-09T10:00:01Z",
      })),
    );
    renderApp(`/knowledge-bases/${IT.id}`);
    expect(await screen.findByRole("heading", { name: "IT Procedures", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("No description.")).toBeInTheDocument();
    const stats = Object.fromEntries(
      Array.from(document.querySelectorAll("main dt")).map((dt) => [dt.textContent, dt.nextSibling.textContent]),
    );
    expect(stats).toMatchObject({ Documents: "3", Conversations: "2" });
    expect(screen.getByRole("banner")).toHaveTextContent("Knowledge bases");
  });

  it("says not found for a missing (or someone else's) knowledge base", async () => {
    getKnowledgeBase.mockRejectedValue(notFound());
    renderApp("/knowledge-bases/not-yours");
    expect(
      await screen.findByRole("heading", { name: "Knowledge base not found" }),
    ).toBeInTheDocument();
    const main = screen.getByRole("main");
    expect(within(main).getByRole("link", { name: "Knowledge bases" })).toHaveAttribute(
      "href",
      "/knowledge-bases",
    );
  });

  it("returns to the list with a notice after deleting", async () => {
    getKnowledgeBase.mockResolvedValue(HR);
    deleteKnowledgeBase.mockResolvedValue();
    listKnowledgeBases.mockResolvedValue([IT]);
    renderApp(`/knowledge-bases/${HR.id}`);
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));

    expect(await screen.findByRole("heading", { name: "Knowledge bases" })).toBeInTheDocument();
    // Wait for the list: while it loads, the spinner is a second role="status" element.
    expect(await screen.findByRole("link", { name: "IT Procedures" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent('Deleted "HR Policies".');
  });

  it("edits the description and shows the saved version", async () => {
    getKnowledgeBase.mockResolvedValue(HR);
    updateKnowledgeBase.mockResolvedValue({ ...HR, description: null });
    renderApp(`/knowledge-bases/${HR.id}`);
    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    await userEvent.clear(screen.getByLabelText("Description (optional)"));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("No description.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "No documents yet" })).toBeInTheDocument();
  });
});

describe("dashboard", () => {
  it("adds up the counts across knowledge bases", async () => {
    renderApp("/dashboard");
    const totals = await screen.findByRole("region", { name: "Totals" });
    expect(totals).toHaveTextContent("2Knowledge bases");
    expect(totals).toHaveTextContent("3Documents");
    expect(totals).toHaveTextContent("2Conversations");
    expect(screen.getByText(/Welcome back, Ana/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /IT Procedures/ })).toHaveAttribute(
      "href",
      `/knowledge-bases/${IT.id}`,
    );
  });

  it("offers to create the first knowledge base", async () => {
    listKnowledgeBases.mockResolvedValue([]);
    renderApp("/dashboard");
    expect(await screen.findByRole("heading", { name: "Start with a knowledge base" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "New knowledge base" }));
    expect(screen.getByRole("dialog", { name: "New knowledge base" })).toBeInTheDocument();
  });
});
