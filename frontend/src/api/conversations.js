import { createSseParser } from "../utils/sse";
import { api, ApiError, reportUnauthorized, toApiError } from "./client";
import { isAll } from "./scope";

const enc = encodeURIComponent;

/** The user's conversations about one knowledge base, most recently active first. */
/** The conversations of one knowledge base, or (ALL_KBS) those across all of them (M16b). */
export async function listConversations(kbId, { signal } = {}) {
  const url = isAll(kbId) ? "/conversations" : `/knowledge-bases/${enc(kbId)}/conversations`;
  const { data } = await api.get(url, { signal });
  return data.items;
}

/** {id, kb_id, title, created_at, updated_at, messages: [{id, role, content, citations, ...}]} */
export async function getConversation(conversationId, { signal } = {}) {
  const { data } = await api.get(`/conversations/${enc(conversationId)}`, { signal });
  return data;
}

export async function renameConversation(conversationId, title) {
  const { data } = await api.patch(`/conversations/${enc(conversationId)}`, { title });
  return data;
}

export async function deleteConversation(conversationId) {
  await api.delete(`/conversations/${enc(conversationId)}`);
}

/**
 * If no event arrives for this long, the answer is given up. The backend bounds each step (the
 * LLM call has 60 s, retries included); the first question after a server restart can wait ~100 s
 * for the embedding model to load (L60), which this covers.
 */
export const IDLE_TIMEOUT_MS = 120_000;

const INTERRUPTED = "The answer stopped before it was complete. Please try again.";

/**
 * Ask a question and receive the answer as Server-Sent Events: a first question starts a new
 * conversation in `kbId`, otherwise it's a follow-up in `conversationId`. With `documentId`, only
 * that document of the knowledge base is searched.
 *
 * Calls `onEvent(name, data)` for `conversation`, `status`, `token`, `citations` and `done`.
 * Rejects with an ApiError for anything that went wrong, including an `error` event (its code and
 * message), a stream that ends without `done`, a cancel (code "aborted") or a stall
 * (IDLE_TIMEOUT_MS, code "timeout").
 *
 * fetch(), not Axios or EventSource: EventSource can only GET, and Axios can't read a response
 * body while it is still arriving in the browser.
 */
export async function streamAnswer({
  kbId,
  conversationId,
  question,
  documentId,
  multiQuery,
  signal,
  onEvent,
}) {
  const url = conversationId
    ? `/api/conversations/${enc(conversationId)}/messages`
    : isAll(kbId)
      ? "/api/conversations" // a new conversation across all knowledge bases (M16b)
      : `/api/knowledge-bases/${enc(kbId)}/conversations`;
  const controller = new AbortController();
  const cancel = () => controller.abort();
  if (signal?.aborted) cancel();
  signal?.addEventListener("abort", cancel);
  let timedOut = false;
  let idleTimer = null;
  const resetIdle = () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, IDLE_TIMEOUT_MS);
  };

  function failure() {
    if (timedOut) {
      return new ApiError({ code: "timeout", message: "The server stopped responding. Please try again." });
    }
    if (controller.signal.aborted) {
      return new ApiError({ code: "aborted", message: "The request was cancelled." });
    }
    return new ApiError({
      code: "network_error",
      message: "Can't reach the server. Check your network connection.",
    });
  }

  try {
    resetIdle();
    let response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        // documentId: answer from that document of the knowledge base only (M14);
        // multiQuery false: the user turned extra phrasings off in Settings (M16)
        body: JSON.stringify({
          question,
          ...(documentId && { document_id: documentId }),
          ...(multiQuery === false && { multi_query: false }),
        }),
        credentials: "same-origin",
        signal: controller.signal,
      });
    } catch {
      throw failure();
    }

    if (!response.ok) {
      // A JSON error from FastAPI (401, 404, 422, 503 ...) or a proxy error: same handling as Axios.
      let body = null;
      try {
        body = await response.json();
      } catch {
        // not JSON: the Vite proxy couldn't reach the backend
      }
      const error = toApiError({
        response: {
          status: response.status,
          data: body,
          headers: { "x-request-id": response.headers.get("x-request-id") },
        },
      });
      if (error.status === 401) reportUnauthorized(error);
      throw error;
    }

    let ending = null; // "done" or the error event's data
    const parser = createSseParser((name, raw) => {
      let data;
      try {
        data = JSON.parse(raw);
      } catch {
        return; // not one of ours
      }
      if (name === "error") {
        ending = data;
        return;
      }
      if (name === "done") ending = "done";
      onEvent(name, data);
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    for (;;) {
      let chunk;
      try {
        chunk = await reader.read();
      } catch {
        throw failure();
      }
      if (chunk.done) break;
      resetIdle();
      parser.push(decoder.decode(chunk.value, { stream: true }));
    }
    parser.push(decoder.decode());

    if (ending === "done") return;
    if (ending) {
      throw new ApiError({
        status: null,
        code: ending.code ?? "internal_error",
        message: ending.message ?? INTERRUPTED,
      });
    }
    throw new ApiError({ code: "stream_interrupted", message: INTERRUPTED });
  } finally {
    clearTimeout(idleTimer);
    signal?.removeEventListener("abort", cancel);
  }
}
