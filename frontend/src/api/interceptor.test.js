import { AxiosError } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, fieldErrors, setUnauthorizedHandler } from "./client";

// Replace the network layer: every request "fails" with the given status.
function respondWith(status) {
  api.defaults.adapter = async (config) => {
    const error = new AxiosError("fail", "ERR_BAD_REQUEST", config);
    error.response = { status, data: { error: { code: "unauthorized", message: "x" } }, config };
    throw error;
  };
}

afterEach(() => setUnauthorizedHandler(null));

describe("session expiry", () => {
  it("reports a 401 from a normal endpoint as an expired session", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    respondWith(401);
    await expect(api.get("/knowledge-bases")).rejects.toMatchObject({ code: "unauthorized" });
    expect(handler).toHaveBeenCalledOnce();
  });

  it("treats 401 from the sign-in checks as a normal answer", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    respondWith(401);
    await expect(api.get("/auth/me")).rejects.toBeTruthy();
    await expect(api.post("/auth/login", {})).rejects.toBeTruthy();
    expect(handler).not.toHaveBeenCalled();
  });
});

describe("fieldErrors", () => {
  it("maps validation details to field names", () => {
    const details = [
      { field: "body.email", message: "bad email" },
      { field: "body.password", message: "too short" },
      { field: "body.password", message: "second message is ignored" },
    ];
    expect(fieldErrors({ details })).toEqual({ email: "bad email", password: "too short" });
    expect(fieldErrors(null)).toEqual({});
  });
});
