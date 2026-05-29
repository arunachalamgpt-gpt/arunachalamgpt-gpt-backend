"""Database engine, connection pool, and session lifecycle.

- Builds a SQLAlchemy `QueuePool`-backed engine sized from `app.config`
- Hooks pool `connect`/`checkout`/`checkin` events for observability
- `verify_connection()` runs `SELECT 1` at startup and surfaces failures loudly
- `init_tables()` runs `SQLModel.metadata.create_all` after importing models
- `get_db()` is the FastAPI dependency: yields a session, rolls back on
  exception, and always closes (no leaked dirty transactions)

Sessions are `sqlmodel.Session`, which subclasses SQLAlchemy's `Session`, so all
SQLAlchemy patterns (`db.execute`, `db.add`, `db.get`, `db.flush`) work
unchanged.
"""

import logging

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool
from sqlmodel import Session, SQLModel

from app.config import (
    DB_CONNECTION_STRING,
    DB_ECHO,
    DB_MAX_OVERFLOW,
    DB_POOL_RECYCLE,
    DB_POOL_SIZE,
    DB_POOL_TIMEOUT,
)

logger = logging.getLogger(__name__)

def build_engine(url: str):
    """Build the SQLAlchemy engine.

    SQLite gets `StaticPool` + `check_same_thread=False` so a single in-memory
    DB is shared across threads (needed for the test suite). Postgres uses the
    standard `QueuePool` with the tuning from `app.config`.
    """
    if url.startswith("sqlite"):
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=DB_ECHO,
        )
    return create_engine(
        url,
        poolclass=QueuePool,
        pool_size=DB_POOL_SIZE,
        max_overflow=DB_MAX_OVERFLOW,
        pool_timeout=DB_POOL_TIMEOUT,
        pool_recycle=DB_POOL_RECYCLE,
        pool_pre_ping=True,
        echo=DB_ECHO,
    )


engine = build_engine(DB_CONNECTION_STRING)

SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=Session
)


@event.listens_for(engine, "connect")
def _on_connect(dbapi_conn, conn_record):
    logger.info("DB connection established (conn_id=%s)", id(dbapi_conn))


@event.listens_for(engine, "checkout")
def _on_checkout(dbapi_conn, conn_record, conn_proxy):
    logger.debug("DB connection checked out from pool (conn_id=%s)", id(dbapi_conn))


@event.listens_for(engine, "checkin")
def _on_checkin(dbapi_conn, conn_record):
    logger.debug("DB connection returned to pool (conn_id=%s)", id(dbapi_conn))


def verify_connection() -> None:
    """Round-trip `SELECT 1` against the DB; raise on failure.

    Called from the FastAPI lifespan so startup fails loudly if Supabase is
    unreachable instead of letting the first request 500.
    """
    logger.info(
        "Verifying DB connection (pool_size=%s, max_overflow=%s)",
        DB_POOL_SIZE,
        DB_MAX_OVERFLOW,
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("DB connection verified successfully")
    except SQLAlchemyError as exc:
        logger.exception("DB connection verification FAILED: %s", exc)
        raise


def init_tables() -> None:
    """Create any missing tables defined under `app.models`.

    Convenient for dev; production should run Alembic migrations instead so
    column changes don't silently fail to apply.
    """
    import app.models  # noqa: F401  — register SQLModel tables
    SQLModel.metadata.create_all(bind=engine)
    logger.info("DB tables ensured (SQLModel.metadata.create_all)")


def get_db():
    """FastAPI dependency yielding a `Session`.

    Rolls back on any exception so failed requests cannot leak dirty
    transactions back to the pool, and always closes the session.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
