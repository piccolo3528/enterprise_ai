import { api } from "./client";

// The session lives in an httpOnly cookie that the browser sends automatically; this code never
// sees the token, so neither can an injected script.

export async function register({ email, password, fullName }) {
  const { data } = await api.post("/auth/register", { email, password, full_name: fullName });
  return data;
}

export async function login({ email, password }) {
  const { data } = await api.post("/auth/login", { email, password });
  return data;
}

export async function logout() {
  await api.post("/auth/logout");
}

/** The signed-in user, or rejects with ApiError code "unauthorized". */
export async function getMe() {
  const { data } = await api.get("/auth/me");
  return data;
}
