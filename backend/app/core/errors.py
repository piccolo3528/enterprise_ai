"""One JSON shape for every error the API returns.

    {"error": {"code": "not_found", "message": "Knowledge base not found",
               "request_id": "3f9c0a1b2d4e"}}

- `code` is stable and machine-readable (the frontend switches on it).
- `message` is safe to show to the user.
- `request_id` matches the server log line, so a user's screenshot leads straight to the log.

Unexpected exceptions return a generic 500 (handled in `core/middleware.py`, which explains
why). The traceback goes to the server log only; stack traces, SQL and file paths never reach the
browser.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var


class AppError(Exception):
    """Base class for errors the services raise on purpose. Routes don't need try/except."""

    status_code = 400
    code = "bad_request"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"


# Codes for errors raised by FastAPI/Starlette itself (unknown route, wrong method, ...).
_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    429: "rate_limited",
}


def error_body(code: str, message: str, **extra) -> dict:
    return {
        "error": {"code": code, "message": message, "request_id": request_id_var.get(), **extra}
    }


async def _app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(error_body(exc.code, exc.message), status_code=exc.status_code)


async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_CODES.get(exc.status_code, "http_error")
    return JSONResponse(
        error_body(code, str(exc.detail)),
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
    )


def _readable(err: dict) -> str:
    # Our own validators raise ValueError("Enter a name"); pydantic reports that as
    # "Value error, Enter a name". The prefix means nothing to the person reading the form.
    message = err["msg"]
    if err["type"] == "value_error":
        message = message.removeprefix("Value error, ")
    return message


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # FastAPI's default response echoes the submitted value ("input"). For a login form that
    # would be the password, so we return only where the problem is and what's wrong.
    details = [
        {"field": ".".join(str(p) for p in err["loc"]), "message": _readable(err)}
        for err in exc.errors()
    ]
    return JSONResponse(
        error_body("validation_error", "Some fields are missing or invalid.", details=details),
        status_code=422,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
