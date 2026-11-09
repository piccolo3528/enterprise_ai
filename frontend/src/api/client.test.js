import { AxiosError, CanceledError } from "axios";
import { describe, expect, it } from "vitest";

import { toApiError } from "./client";

function httpError(status, data, headers = {}) {
  const error = new AxiosError("Request failed", "ERR_BAD_RESPONSE");
  error.response = { status, data, headers };
  return error;
}

describe("toApiError", () => {
  it("keeps the backend's code, message and request ID", () => {
    const err = toApiError(
      httpError(404, {
        error: { code: "not_found", message: "Knowledge base not found", request_id: "abc123" },
      }),
    );
    expect(err).toMatchObject({
      status: 404,
      code: "not_found",
      message: "Knowledge base not found",
      requestId: "abc123",
    });
  });

  it("passes validation details through", () => {
    const details = [{ field: "body.email", message: "Field required" }];
    const err = toApiError(
      httpError(422, { error: { code: "validation_error", message: "Invalid", details } }),
    );
    expect(err.details).toEqual(details);
  });

  it("treats a 5xx without our error shape as the backend being unreachable", () => {
    // What the Vite dev proxy returns when FastAPI isn't running.
    const err = toApiError(httpError(500, ""));
    expect(err.code).toBe("backend_unreachable");
    expect(err.message).toMatch(/port 8000/);
  });

  it("reports a timeout", () => {
    expect(toApiError(new AxiosError("timeout", "ECONNABORTED")).code).toBe("timeout");
  });

  it("reports a network failure when no response arrived", () => {
    expect(toApiError(new AxiosError("Network Error", "ERR_NETWORK")).code).toBe("network_error");
  });

  it("recognises a cancelled request", () => {
    expect(toApiError(new CanceledError()).code).toBe("aborted");
  });
});
