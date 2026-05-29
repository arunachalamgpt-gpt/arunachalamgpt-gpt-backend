from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import exception_handlers
from app.errors import LodgeNotFoundError
from app.middleware import RequestContextMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    exception_handlers.register(app)

    class Body(BaseModel):
        x: int

    @app.get("/raise-app")
    def _app_err():
        raise LodgeNotFoundError(details={"lodge_id": "x"})

    @app.get("/raise-http")
    def _http():
        raise HTTPException(status_code=418, detail="teapot")

    @app.post("/validate")
    def _val(b: Body):
        return b

    @app.get("/raise-integrity")
    def _int():
        raise IntegrityError("stmt", {}, Exception("dup"))

    @app.get("/raise-sql")
    def _sql():
        raise SQLAlchemyError("boom")

    @app.get("/raise-unknown")
    def _unk():
        raise RuntimeError("kaboom")

    return app


def test_app_error_handler_envelope():
    with TestClient(_build_app(), raise_server_exceptions=False) as c:
        res = c.get("/raise-app")
        body = res.json()
        assert res.status_code == 404
        assert body["error"]["code"] == "lodge_not_found"
        assert body["error"]["details"] == {"lodge_id": "x"}
        assert "request_id" in body["error"]


def test_http_exception_handler():
    with TestClient(_build_app(), raise_server_exceptions=False) as c:
        res = c.get("/raise-http")
        assert res.status_code == 418
        assert res.json()["error"]["code"] == "http_418"


def test_validation_handler_returns_field_details():
    with TestClient(_build_app(), raise_server_exceptions=False) as c:
        res = c.post("/validate", json={"x": "not-int"})
        body = res.json()
        assert res.status_code == 422
        assert body["error"]["code"] == "validation_failed"
        assert body["error"]["details"]["errors"]


def test_integrity_error_handler():
    with TestClient(_build_app(), raise_server_exceptions=False) as c:
        res = c.get("/raise-integrity")
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "integrity_violation"


def test_sqlalchemy_error_handler():
    with TestClient(_build_app(), raise_server_exceptions=False) as c:
        res = c.get("/raise-sql")
        assert res.status_code == 503
        assert res.json()["error"]["code"] == "database_error"


def test_unhandled_exception_handler():
    with TestClient(_build_app(), raise_server_exceptions=False) as c:
        res = c.get("/raise-unknown")
        assert res.status_code == 500
        assert res.json()["error"]["code"] == "internal_error"
