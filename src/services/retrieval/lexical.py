"""SQLite FTS5 lexical retrieval."""

from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.services.retrieval.scope import sql_scope_clause


def _fts_query(query: str) -> str:
    tokens = re.findall(r"\w+", query.lower())
    if not tokens:
        return '""'
    return " OR ".join(f'"{t}"' for t in tokens[:12])


def lexical_search(
    db: Session,
    query: str,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    limit: int = 50,
) -> list[tuple[str, float, str]]:
    """Return (doc_id, score, content) ranked by BM25-like FTS rank."""
    fts_q = _fts_query(query)
    sql = """
        SELECT sd.id, sd.content,
               bm25(search_fts) AS rank
        FROM search_fts
        JOIN search_documents sd ON sd.id = search_fts.doc_id
        WHERE search_fts MATCH :query
    """
    params: dict = {"query": fts_q, "limit": limit}
    scope_sql, scope_params = sql_scope_clause(session_id=session_id, user_id=user_id)
    if scope_sql:
        sql += f" AND {scope_sql}"
        params.update(scope_params)
    sql += " ORDER BY rank LIMIT :limit"

    rows = db.execute(text(sql), params).fetchall()
    if not rows:
        return []

    ranks = [float(r[2]) for r in rows]
    min_rank, max_rank = min(ranks), max(ranks)
    span = max_rank - min_rank or 1.0

    results: list[tuple[str, float, str]] = []
    for doc_id, content, rank in rows:
        normalized = 1.0 - ((float(rank) - min_rank) / span)
        results.append((doc_id, normalized, content))
    return results
