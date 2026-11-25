import { api } from "./client";

/** GET /api/stats: the dashboard's numbers for the signed-in user (one request, one query). */
export async function getStats({ signal } = {}) {
  const { data } = await api.get("/stats", { signal });
  return data;
}
