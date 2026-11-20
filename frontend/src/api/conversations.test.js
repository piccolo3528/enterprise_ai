import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setUnauthorizedHandler } from "./client";
import { streamAnswer } from "./conversations";

const encoder = new TextEncoder();

/** A fetch() Response whose body arrives in the given chunks. */
function streamed(chunks, { status = 200, json = null } = {}) {
  let index = 0;
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name) => (name === "x-request-id" ? "req-1" : null) },
    json: async () => {
      if (json === null) throw new SyntaxError("not JSON");
      return json;
    },
    body: {
      getReader: () => ({
        read: async () =>
          index < chunks.length ? { done: false, value: encoder.encode(chunks[index++]) } : { done: true },
      }),
    },
  };
}

const event = (name, data) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});
afterEach(() => {
  vi.unstubAllGlobals();
  setUnauthorizedHandler(null);
});

describe("streamAnswer", () => {
  it("starts a conversation with a POST and hands over each event in order", async () => {
    const body = event("conversation", { id: "c1", title: "Leave?" }) + event("token", { text: "Ten " }) +
      event("token", { text: "days [1]." }) + event("citations", []) + event("done", { answer: "Ten days [1]." });
    fetch.mockResolvedValue(streamed([body.slice(0, 30), body.slice(30, 31), body.slice(31)]));
    const seen = [];
    await streamAnswer({ kbId: "kb 1", question: "Leave?", onEvent: (name, data) => seen.push([name, data]) });

    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/api/knowledge-bases/kb%201/conversations");
    expect(init).toMatchObject({ method: "POST", credentials: "same-origin" });
    expect(JSON.parse(init.body)).toEqual({ question: "Leave?" });
    expect(seen.map(([name]) => name)).toEqual(["conversation", "token", "token", "citations", "done"]);
    expect(seen[2][1]).toEqual({ text: "days [1]." });
  });

  it("sends a follow-up to its conversation", async () => {
    fetch.mockResolvedValue(streamed([event("done", {})]));
    await streamAnswer({ kbId: "kb", conversationId: "c1", question: "And then?", onEvent: () => {} });
    expect(fetch.mock.calls[0][0]).toBe("/api/conversations/c1/messages");
  });

  it("rejects with the code and message of an error event", async () => {
    fetch.mockResolvedValue(
      streamed([event("token", { text: "Half" }) + event("error", { code: "rate_limited", message: "Busy." })]),
    );
    await expect(streamAnswer({ kbId: "kb", question: "Q", onEvent: () => {} })).rejects.toMatchObject({
      code: "rate_limited",
      message: "Busy.",
    });
  });

  it("rejects a stream that ends without its done event", async () => {
    fetch.mockResolvedValue(streamed([event("token", { text: "Half" })]));
    await expect(streamAnswer({ kbId: "kb", question: "Q", onEvent: () => {} })).rejects.toMatchObject({
      code: "stream_interrupted",
    });
  });

  it("turns an HTTP error into an ApiError and reports an expired session", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    fetch.mockResolvedValue(
      streamed([], { status: 401, json: { error: { code: "unauthorized", message: "Please sign in." } } }),
    );
    await expect(streamAnswer({ kbId: "kb", question: "Q", onEvent: () => {} })).rejects.toMatchObject({
      status: 401,
      code: "unauthorized",
      requestId: "req-1",
    });
    expect(onUnauthorized).toHaveBeenCalledOnce();

    fetch.mockResolvedValue(streamed([], { status: 502 })); // the Vite proxy: backend down
    await expect(streamAnswer({ kbId: "kb", question: "Q", onEvent: () => {} })).rejects.toMatchObject({
      code: "backend_unreachable",
    });
  });

  it("reports a cancel as aborted and a network failure as such", async () => {
    const controller = new AbortController();
    fetch.mockImplementation((url, init) => {
      controller.abort();
      return Promise.reject(Object.assign(new Error("aborted"), { name: "AbortError", init }));
    });
    await expect(
      streamAnswer({ kbId: "kb", question: "Q", signal: controller.signal, onEvent: () => {} }),
    ).rejects.toMatchObject({ code: "aborted" });

    fetch.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(streamAnswer({ kbId: "kb", question: "Q", onEvent: () => {} })).rejects.toMatchObject({
      code: "network_error",
    });
  });
});
