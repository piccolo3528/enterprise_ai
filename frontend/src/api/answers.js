import { api } from "./client";

/**
 * An answer is retrieval plus one Gemini call; the backend gives the call (retries included) at
 * most 60 s, so the browser waits a little longer than that instead of the default 30 s.
 */
export const ASK_TIMEOUT_MS = 75_000;

/**
 * Ask one knowledge base a question. Resolves to {answer, not_found, citations, notices, model,
 * prompt_tokens, output_tokens, sources_given, invalid_citations, prompt_version, timings_ms}.
 * `answer` is Markdown with [n] markers that match `citations[].number`.
 */
export async function askKnowledgeBase(kbId, question, { signal } = {}) {
  const { data } = await api.post(
    `/knowledge-bases/${encodeURIComponent(kbId)}/ask`,
    { question },
    { signal, timeout: ASK_TIMEOUT_MS },
  );
  return data;
}
