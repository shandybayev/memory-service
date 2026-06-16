"""Database engine and session management."""

from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings
from src.db.models import Base

_engine = None
_SessionLocal = None


def _configure_sqlite(connection, _):
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        connect_args = {}
        if settings.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(settings.database_url, connect_args=connect_args)
        if settings.database_url.startswith("sqlite"):
            event.listen(_engine, "connect", _configure_sqlite)
        _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    return _engine


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _init_fts(engine)


def _init_fts(engine) -> None:
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
                    doc_id UNINDEXED,
                    content,
                    tokenize='porter unicode61'
                )
                """
            )
        )
        conn.commit()


def get_db() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        get_engine()
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
