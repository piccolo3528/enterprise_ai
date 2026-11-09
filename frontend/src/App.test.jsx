import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import App from "./App";

vi.mock("./api/health", () => ({ getHealth: vi.fn(() => new Promise(() => {})) }));

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("App routing and layout", () => {
  it("sends the home page to the status page", () => {
    renderAt("/");
    expect(screen.getByRole("heading", { name: "System status" })).toBeInTheDocument();
  });

  it("shows a not-found page for unknown routes", () => {
    renderAt("/no-such-page");
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });

  it("treats a not-yet-built page as not found, top bar included", () => {
    renderAt("/knowledge-bases");
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("banner")).toHaveTextContent("Page not found");
  });

  it("links only to pages that exist; the rest are marked Soon", () => {
    renderAt("/status");
    const nav = screen.getByRole("navigation", { name: "Main" });
    const links = Array.from(nav.querySelectorAll("a")).map((a) => a.textContent);
    expect(links).toEqual(["System status"]);
    expect(nav).toHaveTextContent("Knowledge basesSoon");
  });
});
