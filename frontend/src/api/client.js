import axios from "axios";

/**
 * One Axios instance for the whole app. Requests go to "/api/..." on the same origin; in
 * development Vite proxies them to FastAPI (see vite.config.js).
 */
export const api = axios.create({
  baseURL: "/api",
  // The health check allows 15 s per service (a database waking from scale-to-zero), so give
  // the whole request a little more.
  timeout: 30_000,
});

/** The single error type every API call rejects with, whatever went wrong. */
export class ApiError extends Error {
  constructor({ status = null, code, message, requestId = null, details = null }) {
    super(message);
    this.name = "ApiError";
    this.status = status; // HTTP status, or null if no response arrived
    this.code = code; // stable, machine-readable: "not_found", "backend_unreachable", ...
    this.requestId = requestId; // matches the backend log line (X-Request-ID)
    this.details = details; // field-level validation problems, when present
  }
}

/** Turn any Axios failure into an ApiError with a message that is safe to show. */
export function toApiError(error) {
  if (axios.isCancel(error)) {
    return new ApiError({ code: "aborted", message: "The request was cancelled." });
  }

  const response = error.response;
  if (response) {
    // The backend's uniform error shape: {"error": {"code", "message", "request_id", ...}}
    const body = response.data?.error;
    if (body?.code) {
      return new ApiError({
        status: response.status,
        code: body.code,
        message: body.message,
        requestId: body.request_id ?? response.headers?.["x-request-id"] ?? null,
        details: body.details ?? null,
      });
    }
    // A 5xx without our shape didn't come from FastAPI: it's the Vite proxy reporting that it
    // couldn't reach the backend at all.
    if (response.status >= 500) {
      return new ApiError({
        status: response.status,
        code: "backend_unreachable",
        message: "Can't reach the backend. Is the FastAPI server running on port 8000?",
      });
    }
    return new ApiError({
      status: response.status,
      code: "http_error",
      message: `Unexpected response from the server (HTTP ${response.status}).`,
    });
  }

  if (error.code === "ECONNABORTED" || error.code === "ETIMEDOUT") {
    return new ApiError({
      code: "timeout",
      message: "The server took too long to respond. Please try again.",
    });
  }
  return new ApiError({
    code: "network_error",
    message: "Can't reach the server. Check your network connection.",
  });
}

api.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(toApiError(error)),
);
