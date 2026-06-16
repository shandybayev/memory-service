"""Recall and search orchestration."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.api.schemas import RecallRequest, RecallResponse, SearchRequest, SearchResponse, SearchResultSchema
from src.services.formatting.context import ContextFormatter
from src.services.retrieval.hybrid import HybridRetriever


class RecallService:
    def __init__(self) -> None:
        self.retriever = HybridRetriever()
        self.formatter = ContextFormatter()

    def recall(self, db: Session, payload: RecallRequest) -> RecallResponse:
        hits = self.retriever.recall_candidates(
            db,
            payload.query,
            session_id=payload.session_id,
            user_id=payload.user_id,
            limit=40,
        )
        return self.formatter.build_recall(payload.query, hits, payload.max_tokens)

    def search(self, db: Session, payload: SearchRequest) -> SearchResponse:
        hits = self.retriever.search(
            db,
            payload.query,
            session_id=payload.session_id,
            user_id=payload.user_id,
            limit=payload.limit,
        )
        results = [
            SearchResultSchema(
                content=h.content,
                score=round(h.score, 4),
                session_id=h.session_id or "",
                timestamp=h.timestamp,
                metadata=h.metadata,
            )
            for h in hits
        ]
        return SearchResponse(results=results)
