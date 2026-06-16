"""Shared pytest helpers."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")

from src.api import dependencies as deps
from src.db import session as db_module
from src.db.models import Base
from src.db.session import _init_fts
from src.main import app


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    _init_fts(engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    db_module._engine = engine
    db_module._SessionLocal = TestingSession

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.db_dep] = override_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    db_module._engine = None
    db_module._SessionLocal = None


def post_turn(client: TestClient, **kwargs) -> dict:
    payload = {
        "session_id": kwargs.get("session_id", "sess-1"),
        "user_id": kwargs.get("user_id", "user-1"),
        "messages": kwargs.get(
            "messages",
            [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"},
            ],
        ),
        "timestamp": kwargs.get("timestamp", "2025-01-15T10:00:00Z"),
        "metadata": kwargs.get("metadata", {}),
    }
    response = client.post("/turns", json=payload)
    assert response.status_code == 201, response.text
    return response.json()
