import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getMe } from "./api/auth";
import { renderApp, TEST_USER } from "./test/renderApp";

vi.mock("./api/health", () => ({ getHealth: vi.fn(() => new Promise(() => {})) }));
vi.mock("./api/knowledgeBases", () => ({ listKnowledgeBases: vi.fn(() => Promise.resolve([])) }));
vi.mock("./api/auth", () => ({
  getMe: vi.fn(),
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
}));

beforeEach(() => {
  getMe.mockReset();
  getMe.mockResolvedValue(TEST_USER); // signed in for these layout tests
});

describe("App routing and layout (signed in)", () => {
  it("sends the home page to the dashboard", async () => {
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("banner")).toHaveTextContent("Dashboard");
  });

  it("shows a not-found page for unknown routes", async () => {
    renderApp("/no-such-page");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });

  it("treats a not-yet-built page as not found, top bar included", async () => {
    renderApp("/chat");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("banner")).toHaveTextContent("Page not found");
  });

  it("links only to pages that exist; the rest are marked Soon", async () => {
    renderApp("/status");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    const links = Array.from(nav.querySelectorAll("a")).map((a) => a.textContent);
    expect(links).toEqual(["Dashboard", "Knowledge bases", "Search", "System status"]);
    expect(nav).toHaveTextContent("ChatSoon");
  });

  it("shows who is signed in", async () => {
    renderApp("/status");
    const banner = await screen.findByRole("banner");
    expect(banner).toHaveTextContent("Ana Silva");
    expect(banner).toHaveTextContent("AS");
  });
});
