import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import database


def test_get_db_yields_and_closes(engine, monkeypatch):
    monkeypatch.setattr(database, "SessionLocal", lambda: _FakeSession())
    gen = database.get_db()
    session = next(gen)
    with pytest.raises(StopIteration):
        next(gen)
    assert session.closed is True


def test_get_db_rolls_back_on_exception(monkeypatch):
    fake = _FakeSession()
    monkeypatch.setattr(database, "SessionLocal", lambda: fake)
    gen = database.get_db()
    next(gen)
    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("boom"))
    assert fake.rolled_back is True
    assert fake.closed is True


def test_verify_connection_success():
    database.verify_connection()


def test_verify_connection_failure(monkeypatch):
    class _BoomConn:
        def __enter__(self):
            raise SQLAlchemyError("down")

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(database.engine, "connect", lambda: _BoomConn())
    with pytest.raises(SQLAlchemyError):
        database.verify_connection()


def test_init_tables_runs():
    database.init_tables()


def test_build_engine_for_postgres():
    eng = database.build_engine("postgresql://user:pass@localhost/db")
    assert eng.dialect.name == "postgresql"
    assert eng.pool.__class__.__name__ in {"QueuePool", "AsyncAdaptedQueuePool"}
    eng.dispose()


def test_build_engine_for_sqlite():
    eng = database.build_engine("sqlite:///:memory:")
    assert eng.dialect.name == "sqlite"
    assert eng.pool.__class__.__name__ == "StaticPool"
    eng.dispose()


def test_pool_event_listeners_invoked(caplog):
    with caplog.at_level("INFO", logger="app.database"):
        with database.engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))


class _FakeSession:
    def __init__(self):
        self.closed = False
        self.rolled_back = False

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True
