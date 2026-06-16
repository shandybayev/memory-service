"""FastAPI dependencies."""

from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from src.core.config import Settings, get_settings
from src.db.session import get_db


def settings_dep() -> Settings:
    return get_settings()


def db_dep() -> Generator[Session, None, None]:
    yield from get_db()


async def read_body_with_limit(request: Request) -> bytes:
    settings = get_settings()
    body = await request.body()
    if len(body) > settings.max_turn_payload_bytes:
        from src.core.errors import PayloadTooLargeError

        raise PayloadTooLargeError(settings.max_turn_payload_bytes)
    return body
