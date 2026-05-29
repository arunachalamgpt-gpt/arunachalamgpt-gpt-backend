"""Shared pytest fixtures.

Critical: this file points `DB_CONNECTION_STRING` at an in-memory SQLite
**before** any `app.*` module is imported, so the production engine is never
constructed against the live Supabase URL during a test run.
"""

import os

os.environ["DB_CONNECTION_STRING"] = "sqlite:///:memory:"
os.environ["APP_RELOAD"] = "false"
os.environ["LOCAL_TZ_OFFSET_MINUTES"] = "330"

from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

import app.models  # noqa: F401 — register tables
from app.database import get_db
from app.main import app
from app.models.lodge import Lodge


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    try:
        yield eng
    finally:
        SQLModel.metadata.drop_all(eng)
        eng.dispose()


@pytest.fixture
def db_session(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(engine):
    def _override_get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def future_date():
    return date.today() + timedelta(days=7)


@pytest.fixture
def make_lodge(db_session):
    def _factory(*, verified: bool = True, **overrides) -> Lodge:
        defaults = {
            "id": uuid4(),
            "name": "Murugan Residency",
            "address": "12, Car Street, Tiruvannamalai",
            "phone": "9444444444",
            "walk_minutes_to_temple": 8,
            "room_types": ["double"],
            "price_normal": 800,
            "price_pournami": 1200,
            "facilities": ["AC"],
            "payment_accepted": ["cash", "upi"],
            "photo_urls": [],
            "verified": verified,
        }
        defaults.update(overrides)
        lodge = Lodge(**defaults)
        db_session.add(lodge)
        db_session.commit()
        db_session.refresh(lodge)
        return lodge

    return _factory
