"""Hybrid retrieval combining lexical, semantic, and boosts."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.db.models import Memory, SearchDocument
from src.services.retrieval.fusion import reciprocal_rank_fusion
from src.services.retrieval.lexical import lexical_search
from src.services.retrieval.scope import apply_search_scope
from src.services.retrieval.semantic import SemanticEncoder

logger = logging.getLogger(__name__)


@dataclass
class RetrievalHit:
    doc_id: str
    content: str
    score: float
    session_id: str | None
    user_id: str | None
    timestamp: datetime
    metadata: dict
    turn_id: str | None


class HybridRetriever:
    def __init__(self) -> None:
        self.encoder = SemanticEncoder()

    def search(
        self,
        db: Session,
        query: str,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 10,
    ) -> list[RetrievalHit]:
        docs = self._scoped_documents(db, session_id=session_id, user_id=user_id)
        if not docs:
            return []

        lexical_hits = lexical_search(
            db, query, session_id=session_id, user_id=user_id, limit=limit * 5
        )
        lexical_ranked = [(doc_id, score) for doc_id, score, _ in lexical_hits]

        doc_map = {d.id: d for d in docs}
        texts = [d.content for d in docs]
        semantic_scores = self.encoder.similarity(query, texts)
        semantic_ranked = sorted(
            [(d.id, float(semantic_scores[i])) for i, d in enumerate(docs)],
            key=lambda x: x[1],
            reverse=True,
        )[: limit * 5]

        fused = reciprocal_rank_fusion([lexical_ranked, semantic_ranked])
        settings = get_settings()

        hits: list[RetrievalHit] = []
        for doc_id, base_score in sorted(fused.items(), key=lambda x: x[1], reverse=True):
            doc = doc_map.get(doc_id)
            if not doc:
                continue
            score = self._apply_boosts(base_score, doc, query, settings)
            hits.append(
                RetrievalHit(
                    doc_id=doc.id,
                    content=doc.content,
                    score=score,
                    session_id=doc.session_id,
                    user_id=doc.user_id,
                    timestamp=doc.timestamp,
                    metadata=doc.metadata_ or {},
                    turn_id=doc.metadata_.get("turn_id") if doc.metadata_ else None,
                )
            )

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    def recall_candidates(
        self,
        db: Session,
        query: str,
        *,
        session_id: str,
        user_id: str | None,
        limit: int = 30,
    ) -> list[RetrievalHit]:
        """Broader recall for context assembly with user + session scope."""
        user_hits: list[RetrievalHit] = []
        session_hits: list[RetrievalHit] = []

        if user_id:
            active_memories = (
                db.query(Memory)
                .filter(Memory.user_id == user_id, Memory.active.is_(True))
                .all()
            )
            for mem in active_memories:
                if self._query_matches_memory(query, mem):
                    boost = 2.0
                else:
                    boost = 1.2 if mem.type.value == "fact" else 1.0
                user_hits.append(
                    RetrievalHit(
                        doc_id=mem.id,
                        content=f"{mem.type.value}: {mem.key} = {mem.value}",
                        score=mem.confidence * boost,
                        session_id=mem.source_session,
                        user_id=mem.user_id,
                        timestamp=mem.updated_at,
                        metadata={
                            "memory_id": mem.id,
                            "memory_type": mem.type.value,
                            "key": mem.key,
                            "active": mem.active,
                            "turn_id": mem.source_turn,
                            "source": "active_memory",
                        },
                        turn_id=mem.source_turn,
                    )
                )

        session_hits = self.search(
            db, query, session_id=session_id, user_id=user_id, limit=limit
        )
        if user_id:
            global_user_hits = self.search(db, query, user_id=user_id, limit=limit)
            session_hits = self._merge_hits(session_hits, global_user_hits)

        stale_values: set[str] = set()
        if user_id:
            inactive = (
                db.query(Memory)
                .filter(Memory.user_id == user_id, Memory.active.is_(False))
                .all()
            )
            stale_values = {m.value.lower() for m in inactive}

        combined = self._merge_hits(user_hits, session_hits)
        combined = [
            h
            for h in combined
            if h.metadata.get("active") is not False
            and self._include_in_recall(h, stale_values)
        ]
        combined.sort(key=lambda h: h.score, reverse=True)
        return combined[:limit]

    def _scoped_documents(
        self,
        db: Session,
        *,
        session_id: str | None,
        user_id: str | None,
    ) -> list[SearchDocument]:
        q = apply_search_scope(
            db.query(SearchDocument),
            session_id=session_id,
            user_id=user_id,
        )
        docs = q.all()
        return [
            d
            for d in docs
            if not (d.doc_type == "memory" and (d.metadata_ or {}).get("active") is False)
        ]

    def _apply_boosts(self, base_score: float, doc: SearchDocument, query: str, settings) -> float:
        score = base_score
        meta = doc.metadata_ or {}
        if meta.get("doc_type") == "memory" or meta.get("memory_type"):
            score *= 1.15
        if meta.get("active") is True:
            score *= 1.25
        if meta.get("memory_type") == "fact":
            score *= 1.1

        recency = self._recency_factor(doc.timestamp)
        score *= 1.0 + settings.recency_weight * recency

        if any(tok in doc.content.lower() for tok in query.lower().split() if len(tok) > 3):
            score *= 1.1
        return score

    @staticmethod
    def _recency_factor(ts: datetime) -> float:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_days = max((datetime.now(timezone.utc) - ts).total_seconds() / 86400.0, 0.0)
        return math.exp(-age_days / 30.0)

    @staticmethod
    def _query_matches_memory(query: str, mem: Memory) -> bool:
        q = query.lower()
        value = mem.value.lower()
        key = mem.key.split(".")[-1]
        if key in q or value in q:
            return True
        intent_words = ("where", "live", "work", "prefer", "name", "from", "located")
        if any(w in q for w in intent_words):
            if "location" in mem.key and any(w in q for w in ("where", "live", "located", "from")):
                return True
            if "employment" in mem.key and "work" in q:
                return True
            if "preference" in mem.key and "prefer" in q:
                return True
        return False

    @staticmethod
    def _include_in_recall(hit: RetrievalHit, stale_values: set[str]) -> bool:
        if hit.metadata.get("source") == "active_memory" or hit.metadata.get("memory_type"):
            return True
        if stale_values:
            content = hit.content.lower()
            if any(stale in content for stale in stale_values):
                return False
        return True

    @staticmethod
    def _merge_hits(a: list[RetrievalHit], b: list[RetrievalHit]) -> list[RetrievalHit]:
        merged: dict[str, RetrievalHit] = {}
        for hit in a + b:
            existing = merged.get(hit.doc_id)
            if not existing or hit.score > existing.score:
                merged[hit.doc_id] = hit
        return list(merged.values())
