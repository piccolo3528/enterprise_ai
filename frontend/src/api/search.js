import { api } from "./client";
import { isAll } from "./scope";

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
  // ALL_KBS: every knowledge base you have (M16b); each result names its knowledge base
  const url = isAll(kbId) ? "/search" : `/knowledge-bases/${encodeURIComponent(kbId)}/search`;
  const { data } = await api.post(url, body, { signal });
  return data;
}
