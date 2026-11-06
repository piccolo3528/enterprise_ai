"""Every error leaves the API in the same JSON shape, with the request ID and no internals."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import NotFoundError


class LoginForm(BaseModel):
    email: str
    password: str


@pytest.fixture
def client(app):
    # Throwaway routes that fail in each possible way.
    @app.get("/test/not-found")
    def raise_not_found():
        raise NotFoundError("Knowledge base not found")

    @app.get("/test/crash")
    def crash():
        raise RuntimeError("SELECT * FROM users -- internal detail")

    @app.post("/test/login")
    def login(form: LoginForm):
        return {}

    with TestClient(app) as c:
        yield c


def assert_error_shape(response, status, code):
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert error["request_id"] == response.headers["X-Request-ID"]
    return error


def test_app_error_maps_to_its_status_and_code(client):
    error = assert_error_shape(client.get("/test/not-found"), 404, "not_found")
    assert error["message"] == "Knowledge base not found"


def test_unknown_route_uses_the_same_shape(client):
    assert_error_shape(client.get("/api/does-not-exist"), 404, "not_found")


def test_wrong_method_uses_the_same_shape(client):
    assert_error_shape(client.post("/api/health"), 405, "method_not_allowed")


def test_unexpected_exception_returns_generic_500(client, caplog):
    response = client.get("/test/crash")
    error = assert_error_shape(response, 500, "internal_error")
    assert "SELECT" not in response.text  # internals stay on the server...
    assert "RuntimeError" in caplog.text  # ...in the log, with the traceback
    assert error["request_id"] != "-"


def test_validation_error_lists_fields_but_never_echoes_input(client):
    response = client.post("/test/login", json={"password": "hunter2-secret"})
    error = assert_error_shape(response, 422, "validation_error")
    assert {"field": "body.email", "message": "Field required"} in error["details"]
    assert "hunter2-secret" not in response.text
