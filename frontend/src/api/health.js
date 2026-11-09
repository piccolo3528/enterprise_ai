import { api } from "./client";

/** GET /api/health. Resolves to the report; rejects with an ApiError. */
export async function getHealth({ signal } = {}) {
  const { data } = await api.get("/health", { signal });
  return data;
}
