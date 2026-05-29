import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import (
    MaxBodySizeMiddleware,
    RequestContextMiddleware,
    RequestIdFilter,
    request_id_var,
)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=50)

    @app.get("/echo")
    def echo():
        return {"ok": True}

    @app.post("/echo")
    def echo_post(body: dict):
        return body

    return app


def test_request_context_sets_request_id():
    with TestClient(_build_app()) as client:
        res = client.get("/echo")
        assert res.status_code == 200
        assert "x-request-id" in res.headers
        assert len(res.headers["x-request-id"]) >= 16


def test_request_context_propagates_incoming_id():
    with TestClient(_build_app()) as client:
        res = client.get("/echo", headers={"X-Request-ID": "incoming-123"})
        assert res.headers["x-request-id"] == "incoming-123"


def test_max_body_size_rejects_oversize():
    with TestClient(_build_app()) as client:
        big = {"data": "x" * 200}
        res = client.post("/echo", json=big)
        assert res.status_code == 413
        assert res.json()["error"]["code"] == "payload_too_large"


def test_max_body_size_ignores_non_numeric_content_length():
    app = _build_app()
    with TestClient(app) as client:
        res = client.get("/echo", headers={"Content-Length": "not-a-number"})
        assert res.status_code == 200


def test_request_id_filter_populates_record():
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="x", lineno=1,
        msg="m", args=(), exc_info=None,
    )
    token = request_id_var.set("rid-abc")
    try:
        assert RequestIdFilter().filter(record) is True
        assert record.request_id == "rid-abc"
    finally:
        request_id_var.reset(token)
