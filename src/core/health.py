"""Readiness checks for /health."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def readiness_check(db: Session) -> tuple[dict[str, str], bool]:
    """Verify database and FTS availability. Returns (payload, ready)."""
    payload: dict[str, str] = {"status": "ok"}
    ready = True

    try:
        db.execute(text("SELECT 1"))
        payload["database"] = "ok"
    except Exception:
        payload["database"] = "error"
        ready = False

    try:
        db.execute(text("SELECT 1 FROM search_fts LIMIT 1"))
        payload["fts"] = "ok"
    except Exception:
        payload["fts"] = "error"
        ready = False

    if not ready:
        payload["status"] = "degraded"
    return payload, ready
