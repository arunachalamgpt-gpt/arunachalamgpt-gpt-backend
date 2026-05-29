from sqlalchemy.exc import SQLAlchemyError

from app import main as main_module


def test_root(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "running" in res.json()["message"].lower()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_db_check_ok(client):
    res = client.get("/db-check")
    assert res.status_code == 200
    body = res.json()
    assert body["database"] == "connected"
    assert "pool" in body


def test_db_check_failure(client):
    class _Boom:
        def execute(self, *_):
            raise SQLAlchemyError("nope")

    def _boom_db():
        yield _Boom()

    main_module.app.dependency_overrides[main_module.get_db] = _boom_db
    try:
        res = client.get("/db-check")
        assert res.status_code == 503
        assert res.json()["error"]["code"] == "database_error"
    finally:
        main_module.app.dependency_overrides.pop(main_module.get_db, None)


def test_openapi_docs_reachable(client):
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200


def test_lifespan_aborts_when_db_unreachable(monkeypatch):
    import asyncio

    import pytest

    def _boom():
        raise SQLAlchemyError("down")

    monkeypatch.setattr(main_module, "verify_connection", _boom)

    async def _run():
        async with main_module.lifespan(main_module.app):
            pass

    with pytest.raises(SQLAlchemyError):
        asyncio.run(_run())
