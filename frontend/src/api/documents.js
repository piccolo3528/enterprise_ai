import { api } from "./client";
import { listKnowledgeBases } from "./knowledgeBases";
import { isAll } from "./scope";

// Must match the backend (app/services/ingestion/validation.py and MAX_UPLOAD_MB). The browser
// checks first for instant feedback; the server checks again and has the final word.
export const ALLOWED_EXTENSIONS = ["pdf", "docx", "md", "txt"];
export const MAX_UPLOAD_MB = 20;

export async function listDocuments(kbId, { signal } = {}) {
  if (isAll(kbId)) return listAllDocuments({ signal });
  const { data } = await api.get(`/knowledge-bases/${encodeURIComponent(kbId)}/documents`, {
    signal,
  });
  return data.items;
}

/**
 * Every document of every knowledge base, each tagged with `kb_name` (M16b: the document filter
 * of "All knowledge bases"). One request per knowledge base, in parallel: fine for the handful a
 * person has; a cross-KB documents endpoint would be the upgrade.
 */
async function listAllDocuments({ signal } = {}) {
  const knowledgeBases = await listKnowledgeBases({ signal });
  const lists = await Promise.all(
    knowledgeBases.map(async (kb) => {
      const items = await listDocuments(kb.id, { signal });
      return items.map((d) => ({ ...d, kb_name: kb.name }));
    }),
  );
  return lists.flat();
}

/**
 * Upload one file as multipart form data. `onProgress(fraction)` reports 0..1 as bytes leave the
 * browser. Resolves to the new document (status "uploaded"); processing continues on the server.
 */
export async function uploadDocument(kbId, file, { onProgress, signal } = {}) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post(`/knowledge-bases/${encodeURIComponent(kbId)}/documents`, form, {
    signal,
    timeout: 5 * 60_000, // a 20 MB upload on a slow connection takes longer than the default 30 s
    onUploadProgress: (event) => {
      if (onProgress && event.total) onProgress(event.loaded / event.total);
    },
  });
  return data;
}

export async function deleteDocument(id) {
  await api.delete(`/documents/${encodeURIComponent(id)}`);
}

/** Process a failed or ready document again (after a failure, or to rebuild its chunks). */
export async function reprocessDocument(id) {
  const { data } = await api.post(`/documents/${encodeURIComponent(id)}/reprocess`);
  return data;
}

export async function getDocument(id, { signal } = {}) {
  const { data } = await api.get(`/documents/${encodeURIComponent(id)}`, { signal });
  return data;
}

/** One page of a document's chunks, in order: {items, total, offset, limit}. */
export async function listChunks(id, { offset = 0, limit = 50, signal } = {}) {
  const { data } = await api.get(`/documents/${encodeURIComponent(id)}/chunks`, {
    params: { offset, limit },
    signal,
  });
  return data;
}
