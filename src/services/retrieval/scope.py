"""Shared session/user scoping for retrieval."""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Query

from src.db.models import SearchDocument


def apply_search_scope(
    query: Query,
    *,
    session_id: str | None,
    user_id: str | None,
) -> Query:
    if session_id and user_id:
        return query.filter(
            or_(
                SearchDocument.session_id == session_id,
                SearchDocument.user_id == user_id,
            )
        )
    if session_id:
        return query.filter(SearchDocument.session_id == session_id)
    if user_id:
        return query.filter(SearchDocument.user_id == user_id)
    return query


def sql_scope_clause(
    *,
    session_id: str | None,
    user_id: str | None,
    table_alias: str = "sd",
) -> tuple[str, dict]:
    """Build SQL WHERE fragment and params matching apply_search_scope."""
    if session_id and user_id:
        return (
            f"({table_alias}.session_id = :session_id OR {table_alias}.user_id = :user_id)",
            {"session_id": session_id, "user_id": user_id},
        )
    if session_id:
        return (f"{table_alias}.session_id = :session_id", {"session_id": session_id})
    if user_id:
        return (f"{table_alias}.user_id = :user_id", {"user_id": user_id})
    return ("", {})
