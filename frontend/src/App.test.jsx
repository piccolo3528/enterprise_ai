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

  it("shows the not-found page inside the layout, top bar included", async () => {
    renderApp("/reports");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("banner")).toHaveTextContent("Page not found");
  });

  it("links to every page; none is marked Soon any more (Settings arrived in M16)", async () => {
    renderApp("/status");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    const links = Array.from(nav.querySelectorAll("a")).map((a) => a.textContent);
    expect(links).toEqual(["Dashboard", "Knowledge bases", "Chat", "Search", "System status", "Settings"]);
    expect(nav).not.toHaveTextContent("Soon");
  });

  it("shows who is signed in", async () => {
    renderApp("/status");
    const banner = await screen.findByRole("banner");
    expect(banner).toHaveTextContent("Ana Silva");
    expect(banner).toHaveTextContent("AS");
  });
});
