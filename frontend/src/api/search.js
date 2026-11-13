import { api } from "./client";

export const SEARCH_MODES = ["hybrid", "semantic", "keyword"];

/**
 * Search one knowledge base. Resolves to {mode, results, query_terms, notice, timings_ms}.
 * `documentId` limits the search to one document; `minScore` is a minimum cosine similarity
 * for the semantic side.
 */
export async function searchKnowledgeBase(
  kbId,
  { query, mode = "hybrid", topK = 10, documentId, minScore } = {},
  { signal } = {},
) {
  const body = { query, mode, top_k: topK };
  if (documentId) body.document_id = documentId;
  if (minScore != null) body.min_score = minScore;
  const { data } = await api.post(`/knowledge-bases/${encodeURIComponent(kbId)}/search`, body, {
    signal,
  });
  return data;
}
