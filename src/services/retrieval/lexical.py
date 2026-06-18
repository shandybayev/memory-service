"""SQLite FTS5 lexical retrieval."""

from __future__ import annotations

import logging
import re

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from src.services.retrieval.scope import sql_scope_clause

logger = logging.getLogger(__name__)

# FTS5 treats these as syntax; strip from tokenization to reduce parse errors.
_FTS_RESERVED = frozenset({"AND", "OR", "NOT", "NEAR"})


def _fts_query(query: str) -> str | None:
    tokens = re.findall(r"\w+", query.lower())
    tokens = [t for t in tokens if t.upper() not in _FTS_RESERVED][:12]
    if not tokens:
        return None
    return " OR ".join(f'"{t}"' for t in tokens)


def lexical_search(
    db: Session,
    query: str,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    limit: int = 50,
) -> list[tuple[str, float, str]]:
    """Return (doc_id, score, content) ranked by BM25-like FTS rank."""
    if not session_id and not user_id:
        return []
    fts_q = _fts_query(query)
    if fts_q is None:
        return []

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

    try:
        rows = db.execute(text(sql), params).fetchall()
    except OperationalError as exc:
        logger.warning("FTS query failed for %r: %s", query, exc)
        return []
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
