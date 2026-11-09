import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getHealth } from "../api/health";
import { ApiError } from "../api/client";
import SystemStatus, { formatLatency } from "./SystemStatus";

// Replace the real API call: these tests check the page, not the network.
vi.mock("../api/health", () => ({ getHealth: vi.fn() }));

function report(overrides = {}) {
  return {
    status: "ok",
    version: "0.1.0",
    services: {
      database: { status: "ok", latency_ms: 815, detail: null },
      vector_store: {
        status: "ok",
        latency_ms: 245,
        detail: null,
        collection: "chunks",
        collection_exists: false,
      },
      llm: {
        provider: "gemini",
        api_key_configured: true,
        answer_model: "gemini-3.5-flash-lite",
        utility_model: "gemini-3.5-flash-lite",
        fallback_configured: true,
      },
    },
    models: {
      embedding: "BAAI/bge-small-en-v1.5",
      reranker: "cross-encoder/ms-marco-MiniLM-L-6-v2",
    },
    ...overrides,
  };
}

beforeEach(() => {
  getHealth.mockReset();
});

describe("SystemStatus", () => {
  it("shows a loading state, then a healthy report", async () => {
    getHealth.mockResolvedValue(report());
    render(<SystemStatus />);

    expect(screen.getByText("Checking services…")).toBeInTheDocument();
    expect(await screen.findByText("All systems operational")).toBeInTheDocument();
    expect(screen.getByText("815 ms")).toBeInTheDocument();
    expect(screen.getByText("Not yet (on first indexing)")).toBeInTheDocument();
    // Answer and utility model are the same model by default.
    expect(screen.getAllByText("gemini-3.5-flash-lite", { selector: "dd" })).toHaveLength(2);
  });

  it("shows which service is down when the backend reports degraded", async () => {
    const degraded = report({ status: "degraded" });
    degraded.services.database = {
      status: "error",
      latency_ms: 15000,
      detail: "no response within 15 s",
    };
    getHealth.mockResolvedValue(degraded);
    render(<SystemStatus />);

    expect(await screen.findByText("Degraded")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByText("no response within 15 s")).toBeInTheDocument();
  });

  it("shows the error with its reference when the request fails, and retries", async () => {
    getHealth.mockRejectedValueOnce(
      new ApiError({
        code: "backend_unreachable",
        message: "Can't reach the backend. Is the FastAPI server running on port 8000?",
        requestId: "f00dfeed1234",
      }),
    );
    getHealth.mockResolvedValueOnce(report());
    render(<SystemStatus />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Can't reach the backend");
    expect(alert).toHaveTextContent("Reference: f00dfeed1234");

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("All systems operational")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(getHealth).toHaveBeenCalledTimes(2);
  });

  it("never keeps showing an old healthy report after a failed refresh", async () => {
    getHealth.mockResolvedValueOnce(report());
    getHealth.mockRejectedValueOnce(
      new ApiError({ code: "backend_unreachable", message: "Can't reach the backend." }),
    );
    render(<SystemStatus />);
    expect(await screen.findByText("All systems operational")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach the backend.");
    expect(screen.queryByText("All systems operational")).not.toBeInTheDocument();
  });

  it("flags a missing Gemini key", async () => {
    const noKey = report({ status: "degraded" });
    noKey.services.llm.api_key_configured = false;
    getHealth.mockResolvedValue(noKey);
    render(<SystemStatus />);

    expect(await screen.findByText("No API key")).toBeInTheDocument();
  });
});

describe("formatLatency", () => {
  it("formats milliseconds and seconds", () => {
    expect(formatLatency(244.6)).toBe("245 ms");
    expect(formatLatency(1050)).toBe("1.05 s");
    expect(formatLatency(null)).toBe("—");
  });
});
