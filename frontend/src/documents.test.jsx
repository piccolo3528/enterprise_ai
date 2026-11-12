import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getMe } from "./api/auth";
import { ApiError } from "./api/client";
import {
  deleteDocument,
  getDocument,
  listChunks,
  listDocuments,
  reprocessDocument,
  uploadDocument,
} from "./api/documents";
import { getKnowledgeBase } from "./api/knowledgeBases";
import { POLL_INTERVAL_MS } from "./hooks/useDocuments";
import { renderApp, TEST_USER } from "./test/renderApp";

vi.mock("./api/health", () => ({ getHealth: vi.fn(() => new Promise(() => {})) }));
vi.mock("./api/auth", () => ({ getMe: vi.fn(), login: vi.fn(), register: vi.fn(), logout: vi.fn() }));
vi.mock("./api/knowledgeBases", () => ({
  listKnowledgeBases: vi.fn(() => Promise.resolve([])),
  getKnowledgeBase: vi.fn(),
  createKnowledgeBase: vi.fn(),
  updateKnowledgeBase: vi.fn(),
  deleteKnowledgeBase: vi.fn(),
}));
// Keep the real constants (allowed types, size limit); replace only the network calls.
vi.mock("./api/documents", async (importOriginal) => ({
  ...(await importOriginal()),
  listDocuments: vi.fn(),
  uploadDocument: vi.fn(),
  deleteDocument: vi.fn(),
  reprocessDocument: vi.fn(),
  getDocument: vi.fn(),
  listChunks: vi.fn(),
}));

const KB = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "HR Policies",
  description: null,
  document_count: 0,
  conversation_count: 0,
  created_at: "2026-11-09T10:00:00Z",
  updated_at: "2026-11-09T10:00:00Z",
};

function doc(overrides = {}) {
  return {
    id: "d1",
    kb_id: KB.id,
    original_filename: "leave-policy.md",
    file_type: "md",
    size_bytes: 14_540,
    status: "ready",
    error_message: null,
    page_count: null,
    chunk_count: 0,
    metadata: { document_id: "NX-HR-002", version: "3.0", status: "current" },
    created_at: "2026-11-10T09:00:00Z",
    processed_at: "2026-11-10T09:00:01Z",
    ...overrides,
  };
}

const openPage = () => renderApp(`/knowledge-bases/${KB.id}`);
const table = async () => within(await screen.findByRole("table"));

beforeEach(() => {
  vi.clearAllMocks();
  getMe.mockResolvedValue(TEST_USER);
  getKnowledgeBase.mockResolvedValue(KB);
  listDocuments.mockResolvedValue([]);
});

describe("document list", () => {
  it("invites the first upload when the knowledge base is empty", async () => {
    openPage();
    expect(await screen.findByRole("heading", { name: "No documents yet" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Drop files here/ })).toBeInTheDocument();
  });

  it("shows each document's status, metadata and the reason a file failed", async () => {
    listDocuments.mockResolvedValue([
      doc(),
      doc({
        id: "d2",
        original_filename: "scan.pdf",
        file_type: "pdf",
        status: "failed",
        error_message: "No text could be found in this file.",
        metadata: {},
      }),
    ]);
    openPage();
    const rows = (await table()).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("leave-policy.md");
    expect(rows[0]).toHaveTextContent("NX-HR-002 v3.0 · current");
    expect(rows[0]).toHaveTextContent("Ready");
    expect(rows[0]).toHaveTextContent("14.2 KB");
    expect(rows[1]).toHaveTextContent("Failed");
    expect(rows[1]).toHaveTextContent("No text could be found in this file.");
    // The header count follows the live list (updated just after the list renders).
    await waitFor(() =>
      expect(screen.getByText("Documents", { selector: "dt" }).nextSibling).toHaveTextContent("2"),
    );
  });

  it("keeps polling while a document is processing, then stops", async () => {
    listDocuments
      .mockResolvedValueOnce([doc({ status: "processing" })])
      .mockResolvedValue([doc({ status: "ready" })]);
    openPage();
    // The spinner's screen-reader label is also "Processing", so look inside the table row.
    expect((await table()).getAllByText("Processing").length).toBeGreaterThan(0);
    expect(
      await (await table()).findByText("Ready", {}, { timeout: POLL_INTERVAL_MS + 2000 }),
    ).toBeInTheDocument();
    const calls = listDocuments.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS + 300));
    expect(listDocuments.mock.calls.length).toBe(calls); // nothing pending: no more requests
  }, 10_000);
});

describe("uploading", () => {
  it("uploads a chosen file and refreshes the list", async () => {
    uploadDocument.mockImplementation(async (kbId, file, { onProgress }) => {
      onProgress(0.5);
      return doc({ id: "new", original_filename: file.name, status: "uploaded" });
    });
    openPage();
    await screen.findByRole("heading", { name: "No documents yet" });
    listDocuments.mockResolvedValue([doc({ id: "new", original_filename: "policy.md" })]);

    const file = new File(["# Policy"], "policy.md", { type: "text/markdown" });
    await userEvent.upload(screen.getByTestId("file-input"), file);

    expect(uploadDocument).toHaveBeenCalledWith(KB.id, file, expect.anything());
    const uploads = within(screen.getByRole("list", { name: "Uploads" }));
    expect(await uploads.findByText("Uploaded")).toBeInTheDocument();
    expect(await (await table()).findByText("policy.md")).toBeInTheDocument();
  });

  it("accepts files dropped onto the drop zone", async () => {
    uploadDocument.mockResolvedValue(doc({ status: "uploaded" }));
    openPage();
    const zone = await screen.findByRole("button", { name: /Drop files here/ });
    const file = new File(["text"], "notes.txt", { type: "text/plain" });
    fireEvent.drop(zone, { dataTransfer: { files: [file] } });
    await waitFor(() => expect(uploadDocument).toHaveBeenCalledWith(KB.id, file, expect.anything()));
  });

  it("refuses wrong types and oversized files in the browser, without uploading", async () => {
    openPage();
    await screen.findByRole("heading", { name: "No documents yet" });
    const big = new File(["x"], "huge.pdf", { type: "application/pdf" });
    Object.defineProperty(big, "size", { value: 21 * 1024 * 1024 });
    const exe = new File(["MZ"], "setup.exe");
    // applyAccept: false, like dragging a file in: the accept attribute is only a hint.
    await userEvent.upload(screen.getByTestId("file-input"), [exe, big], { applyAccept: false });

    const uploads = within(screen.getByRole("list", { name: "Uploads" }));
    expect(uploads.getByText(/Only PDF, Word/)).toBeInTheDocument();
    expect(uploads.getByText("The file is larger than 20 MB.")).toBeInTheDocument();
    expect(uploadDocument).not.toHaveBeenCalled();
  });

  it("shows the server's reason next to the file it rejected", async () => {
    uploadDocument.mockRejectedValue(
      new ApiError({
        status: 409,
        code: "conflict",
        message: "This exact file is already in this knowledge base.",
      }),
    );
    openPage();
    await screen.findByRole("heading", { name: "No documents yet" });
    await userEvent.upload(screen.getByTestId("file-input"), new File(["a"], "copy.md"));
    const uploads = within(screen.getByRole("list", { name: "Uploads" }));
    expect(await uploads.findByText("This exact file is already in this knowledge base.")).toBeInTheDocument();
    expect(uploads.getByText("Not uploaded")).toBeInTheDocument();
  });
});

describe("document actions", () => {
  it("retries a failed document", async () => {
    listDocuments
      .mockResolvedValueOnce([doc({ status: "failed", error_message: "Interrupted." })])
      .mockResolvedValue([doc({ status: "ready" })]);
    reprocessDocument.mockResolvedValue(doc({ status: "uploaded" }));
    openPage();
    await userEvent.click(await screen.findByRole("button", { name: "Retry leave-policy.md" }));
    expect(reprocessDocument).toHaveBeenCalledWith("d1");
    expect(await (await table()).findByText("Ready")).toBeInTheDocument();
  });

  it("deletes a document after confirmation", async () => {
    listDocuments.mockResolvedValue([doc()]);
    deleteDocument.mockResolvedValue();
    openPage();
    await userEvent.click(await screen.findByRole("button", { name: "Delete leave-policy.md" }));
    const dialog = screen.getByRole("dialog", { name: 'Delete "leave-policy.md"?' });
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    expect(deleteDocument).toHaveBeenCalledWith("d1");
    expect(await screen.findByRole("heading", { name: "No documents yet" })).toBeInTheDocument();
  });

  it("shows a delete that couldn't finish as Deleting, and deleting again completes it", async () => {
    listDocuments
      .mockResolvedValueOnce([doc()])
      .mockResolvedValueOnce([doc({ status: "deleting" })])
      .mockResolvedValue([]);
    deleteDocument
      .mockRejectedValueOnce(
        new ApiError({
          status: 503,
          code: "service_unavailable",
          message: "The search index couldn't be updated right now.",
        }),
      )
      .mockResolvedValue();
    openPage();
    await userEvent.click(await screen.findByRole("button", { name: "Delete leave-policy.md" }));
    let dialog = screen.getByRole("dialog", { name: 'Delete "leave-policy.md"?' });
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "The search index couldn't be updated right now.",
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(await (await table()).findByText("Deleting")).toBeInTheDocument();
    expect(screen.getByText(/Delete it again to complete it/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Delete leave-policy.md" }));
    dialog = screen.getByRole("dialog", { name: 'Delete "leave-policy.md"?' });
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    expect(deleteDocument).toHaveBeenCalledTimes(2);
    expect(await screen.findByRole("heading", { name: "No documents yet" })).toBeInTheDocument();
  });

  it("offers a retry when the list can't be loaded", async () => {
    listDocuments
      .mockRejectedValueOnce(
        new ApiError({ status: 503, code: "backend_unreachable", message: "Can't reach the backend." }),
      )
      .mockResolvedValue([doc()]);
    openPage();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't load the documents");
    await userEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await (await table()).findByText("leave-policy.md")).toBeInTheDocument();
  });
});

function chunk(index, overrides = {}) {
  return {
    id: `c${index}`,
    chunk_index: index,
    text: `NX-HR-002 v3.0 · 4. Entitlements

Chunk ${index} text.`,
    token_count: 100 + index,
    page_start: null,
    page_end: null,
    section: "4. Entitlements › 4.1 Annual entitlement",
    strategy: "heading",
    ...overrides,
  };
}

const inspector = () => renderApp(`/knowledge-bases/${KB.id}/documents/d1`);

describe("chunk inspector", () => {
  it("links ready documents from the table to their chunks", async () => {
    listDocuments.mockResolvedValue([doc({ chunk_count: 16 })]);
    openPage();
    const link = await screen.findByRole("link", { name: "leave-policy.md" });
    expect(link).toHaveAttribute("href", `/knowledge-bases/${KB.id}/documents/d1`);
    expect(link.closest("tr")).toHaveTextContent("16 chunks");
  });

  it("shows each chunk's section, pages and size, a page at a time", async () => {
    getDocument.mockResolvedValue(doc({ chunk_count: 3 }));
    listChunks
      .mockResolvedValueOnce({ items: [chunk(0), chunk(1, { page_start: 2, page_end: 3 })], total: 3, offset: 0, limit: 2 })
      .mockResolvedValueOnce({ items: [chunk(2)], total: 3, offset: 2, limit: 2 });
    inspector();
    const list = within(await screen.findByRole("list", { name: "Chunks" }));
    expect(list.getAllByRole("listitem")).toHaveLength(2);
    expect(list.getAllByText("4. Entitlements › 4.1 Annual entitlement")).toHaveLength(2);
    expect(list.getByText("pp. 2–3")).toBeInTheDocument();
    expect(list.getByText("101 tokens")).toBeInTheDocument();
    expect(screen.getByText(/3 chunks · heading chunking · 101 tokens on average/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() => expect(list.getAllByRole("listitem")).toHaveLength(3));
    expect(listChunks).toHaveBeenLastCalledWith("d1", expect.objectContaining({ offset: 2 }));
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("explains a document from before chunking existed, and reprocesses it", async () => {
    getDocument
      .mockResolvedValueOnce(doc({ chunk_count: 0 }))
      .mockResolvedValue(doc({ chunk_count: 1 }));
    listChunks
      .mockResolvedValueOnce({ items: [], total: 0, offset: 0, limit: 50 })
      .mockResolvedValue({ items: [chunk(0)], total: 1, offset: 0, limit: 50 });
    reprocessDocument.mockResolvedValue(doc({ status: "uploaded" }));
    inspector();
    expect(await screen.findByRole("heading", { name: "No chunks" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reprocess" }));
    expect(reprocessDocument).toHaveBeenCalledWith("d1");
    expect(await screen.findByRole("list", { name: "Chunks" })).toBeInTheDocument();
  });

  it("says not found for a missing (or someone else's) document", async () => {
    getDocument.mockRejectedValue(
      new ApiError({ status: 404, code: "not_found", message: "Document not found." }),
    );
    inspector();
    expect(await screen.findByRole("heading", { name: "Document not found" })).toBeInTheDocument();
  });
});
