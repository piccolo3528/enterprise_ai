import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { changePassword, getMe, logoutEverywhere, updateProfile } from "./api/auth";
import { ApiError } from "./api/client";
import { getHealth } from "./api/health";
import { renderApp, TEST_USER } from "./test/renderApp";

vi.mock("./api/health", () => ({ getHealth: vi.fn() }));
vi.mock("./api/knowledgeBases", () => ({ listKnowledgeBases: vi.fn(() => Promise.resolve([])) }));
vi.mock("./api/auth", () => ({
  getMe: vi.fn(),
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  updateProfile: vi.fn(),
  changePassword: vi.fn(),
  logoutEverywhere: vi.fn(),
}));

const REPORT = {
  status: "ok",
  version: "0.16.0",
  services: {
    database: { status: "ok", latency_ms: 60, detail: null, size_bytes: 52_428_800 },
    vector_store: { status: "ok", latency_ms: 250, detail: null, collection: "chunks", collection_exists: true },
    llm: { provider: "gemini", api_key_configured: true, answer_model: "a", utility_model: "u", fallback_configured: true },
  },
  models: { embedding: "BAAI/bge-small-en-v1.5", reranker: "r" },
  retrieval: {
    chunk_strategy: "auto",
    chunk_size_tokens: 400,
    retrieval_top_k: 20,
    context_max_sources: 10,
    multi_query_enabled: true,
    rerank_enabled: false,
    version_mode: "demote",
    temperature: 0.1,
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  getMe.mockResolvedValue(TEST_USER);
  getHealth.mockResolvedValue(REPORT);
});

function section(name) {
  return screen.getByRole("region", { name });
}

async function openSettings() {
  renderApp("/settings");
  return screen.findByRole("heading", { name: "Settings", level: 1 });
}

describe("settings page", () => {
  it("warns not to use confidential documents and shows every section", async () => {
    await openSettings();
    expect(screen.getByRole("complementary", { name: "Privacy notice" })).toHaveTextContent(
      /free-tier terms allow providers to use that content/,
    );
    for (const name of ["Profile", "Password", "Search and chat defaults", "Sessions", "System status"]) {
      expect(section(name)).toBeInTheDocument();
    }
    expect(within(section("Profile")).getByLabelText("Email")).toHaveAttribute("readonly");
  });

  it("saves a new name and shows it in the top bar", async () => {
    updateProfile.mockResolvedValue({ ...TEST_USER, full_name: "Ana Costa" });
    await openSettings();
    const profile = section("Profile");
    const name = within(profile).getByLabelText("Full name");
    await userEvent.clear(name);
    await userEvent.type(name, "Ana Costa");
    await userEvent.click(within(profile).getByRole("button", { name: "Save name" }));
    expect(updateProfile).toHaveBeenCalledWith({ fullName: "Ana Costa" });
    expect(await within(profile).findByRole("status")).toHaveTextContent("Saved.");
    expect(screen.getByRole("banner")).toHaveTextContent("Ana Costa");
  });

  it("checks the new password before sending it", async () => {
    await openSettings();
    const form = section("Password");
    await userEvent.type(within(form).getByLabelText("Current password"), "old-password");
    await userEvent.type(within(form).getByLabelText("New password"), "short");
    await userEvent.type(within(form).getByLabelText("Confirm new password"), "other");
    await userEvent.click(within(form).getByRole("button", { name: "Change password" }));
    expect(within(form).getByText("Use at least 8 characters.")).toBeInTheDocument();
    expect(within(form).getByText("The passwords don't match.")).toBeInTheDocument();
    expect(changePassword).not.toHaveBeenCalled();
  });

  it("shows the server's answer to a wrong current password, and success clears the form", async () => {
    changePassword.mockRejectedValueOnce(
      new ApiError({ status: 400, code: "bad_request", message: "Your current password is incorrect." }),
    );
    changePassword.mockResolvedValueOnce(undefined);
    await openSettings();
    const form = section("Password");
    const fill = async (current) => {
      await userEvent.clear(within(form).getByLabelText("Current password"));
      await userEvent.type(within(form).getByLabelText("Current password"), current);
      await userEvent.clear(within(form).getByLabelText("New password"));
      await userEvent.type(within(form).getByLabelText("New password"), "a-new-long-password");
      await userEvent.clear(within(form).getByLabelText("Confirm new password"));
      await userEvent.type(within(form).getByLabelText("Confirm new password"), "a-new-long-password");
      await userEvent.click(within(form).getByRole("button", { name: "Change password" }));
    };
    await fill("wrong-one");
    expect(await within(form).findByRole("alert")).toHaveTextContent("Your current password is incorrect.");
    await fill("right-one");
    expect(await within(form).findByRole("status")).toHaveTextContent("signed out on your other devices");
    expect(changePassword).toHaveBeenLastCalledWith({
      currentPassword: "right-one",
      newPassword: "a-new-long-password",
    });
    expect(within(form).getByLabelText("Current password")).toHaveValue("");
  });

  it("saves search and chat defaults, and refuses out-of-range numbers", async () => {
    updateProfile.mockImplementation(async ({ preferences }) => ({ ...TEST_USER, preferences }));
    await openSettings();
    const form = section("Search and chat defaults");
    const results = within(form).getByLabelText("Results per search");
    await userEvent.clear(results);
    await userEvent.type(results, "80");
    await userEvent.click(within(form).getByRole("button", { name: "Save defaults" }));
    expect(within(form).getByText("A whole number from 1 to 50.")).toBeInTheDocument();
    expect(updateProfile).not.toHaveBeenCalled();

    await userEvent.clear(results);
    await userEvent.type(results, "5");
    await userEvent.selectOptions(within(form).getByLabelText("Search mode"), "keyword");
    await userEvent.type(within(form).getByLabelText("Minimum similarity"), "0.5");
    await userEvent.click(within(form).getByRole("checkbox", { name: /extra phrasings/ }));
    await userEvent.click(within(form).getByRole("button", { name: "Save defaults" }));
    expect(updateProfile).toHaveBeenCalledWith({
      preferences: { search_mode: "keyword", search_top_k: 5, search_min_score: 0.5, chat_multi_query: false },
    });
    expect(await within(form).findByRole("status")).toHaveTextContent("Saved.");
  });

  it("signs out everywhere after confirming, back to sign-in with a notice", async () => {
    logoutEverywhere.mockResolvedValue(undefined);
    await openSettings();
    await userEvent.click(within(section("Sessions")).getByRole("button", { name: "Sign out everywhere" }));
    const dialog = screen.getByRole("dialog", { name: "Sign out on every device?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Sign out everywhere" }));
    expect(logoutEverywhere).toHaveBeenCalled();
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByText("You've been signed out on every device.")).toBeInTheDocument();
  });

  it("shows the database storage against Neon's free 1 GB and the server's pipeline settings", async () => {
    await openSettings();
    const status = section("System status");
    expect(await within(status).findByText("All systems operational")).toBeInTheDocument();
    expect(within(status).getByText("50.0 MB (5 %)")).toBeInTheDocument();
    expect(within(status).getByRole("meter", { name: "Database storage used" })).toHaveAttribute(
      "aria-valuenow",
      "5",
    );
    expect(status).toHaveTextContent("Passages given to the AIup to 10 (of 20 found)");
  });

  it("offers a retry when the status check fails", async () => {
    getHealth.mockRejectedValueOnce(new ApiError({ code: "network_error", message: "Can't reach the server." }));
    await openSettings();
    const status = section("System status");
    expect(await within(status).findByRole("alert")).toHaveTextContent("Can't reach the server.");
    await userEvent.click(within(status).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(within(status).getByText("All systems operational")).toBeInTheDocument());
  });
});

describe("a session ended elsewhere", () => {
  it("shows the server's reason on the sign-in page", async () => {
    // The real Axios interceptor isn't used here (the API module is mocked), so call the
    // handler the way it would.
    const { reportUnauthorized } = await import("./api/client");
    await openSettings();
    reportUnauthorized(
      new ApiError({
        status: 401,
        code: "unauthorized",
        message: "You were signed out because your password changed. Please sign in again.",
      }),
    );
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByText(/signed out because your password changed/)).toBeInTheDocument();
  });
});
