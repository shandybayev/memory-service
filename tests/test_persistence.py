"""Persistence across database reinitialization (simulates container restart)."""

import os

import pytest
from fastapi.testclient import TestClient

from src.core.config import get_settings
from src.db import session as db_module
from src.db.session import init_db
from src.main import app


def _reset_db_module() -> None:
    if db_module._engine is not None:
        db_module._engine.dispose()
    db_module._engine = None
    db_module._SessionLocal = None
    get_settings.cache_clear()


@pytest.mark.integration
def test_restart_persistence_simulation(tmp_path):
    db_path = tmp_path / "memory.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    os.environ["DATABASE_URL"] = db_url
    _reset_db_module()

    try:
        init_db()
        with TestClient(app) as client:
            response = client.post(
                "/turns",
                json={
                    "session_id": "sess-persist",
                    "user_id": "user-persist",
                    "messages": [
                        {"role": "user", "content": "I just moved from NYC to Berlin."},
                        {"role": "assistant", "content": "Nice."},
                    ],
                    "timestamp": "2025-03-01T09:00:00Z",
                },
            )
            assert response.status_code == 201

        _reset_db_module()
        init_db()

        with TestClient(app) as client:
            recall = client.post(
                "/recall",
                json={
                    "query": "Where does the user live?",
                    "session_id": "sess-persist",
                    "user_id": "user-persist",
                    "max_tokens": 512,
                },
            )
            assert recall.status_code == 200
            assert "Berlin" in recall.json()["context"]
    finally:
        _reset_db_module()
