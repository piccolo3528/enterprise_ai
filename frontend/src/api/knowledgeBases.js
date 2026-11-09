import { api } from "./client";

// Every call rejects with an ApiError. Someone else's knowledge base (or a deleted one) is a
// plain 404 "not_found": the server never says which.

/** The signed-in user's knowledge bases with counts, most recently changed first. */
export async function listKnowledgeBases({ signal } = {}) {
  const { data } = await api.get("/knowledge-bases", { signal });
  return data.items;
}

export async function getKnowledgeBase(id, { signal } = {}) {
  const { data } = await api.get(`/knowledge-bases/${encodeURIComponent(id)}`, { signal });
  return data;
}

export async function createKnowledgeBase({ name, description }) {
  const { data } = await api.post("/knowledge-bases", { name, description });
  return data;
}

/** PATCH: only the fields passed are changed. An empty description clears it. */
export async function updateKnowledgeBase(id, changes) {
  const { data } = await api.patch(`/knowledge-bases/${encodeURIComponent(id)}`, changes);
  return data;
}

export async function deleteKnowledgeBase(id) {
  await api.delete(`/knowledge-bases/${encodeURIComponent(id)}`);
}
