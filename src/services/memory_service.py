"""User and session data management."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.schemas import MemorySchema
from src.db.models import Memory, SearchDocument, Turn

logger = logging.getLogger(__name__)


class MemoryQueryService:
    def list_user_memories(self, db: Session, user_id: str) -> list[MemorySchema]:
        rows = (
            db.query(Memory)
            .filter(Memory.user_id == user_id)
            .order_by(Memory.created_at.desc())
            .all()
        )
        return [self._to_schema(m) for m in rows]

    @staticmethod
    def _to_schema(memory: Memory) -> MemorySchema:
        return MemorySchema(
            id=memory.id,
            type=memory.type.value,
            key=memory.key,
            value=memory.value,
            confidence=memory.confidence,
            source_session=memory.source_session,
            source_turn=memory.source_turn,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
            supersedes=memory.supersedes,
            active=memory.active,
        )


class DeletionService:
    def delete_session(self, db: Session, session_id: str) -> None:
        db.query(Memory).filter(Memory.source_session == session_id).delete(synchronize_session=False)
        db.query(Turn).filter(Turn.session_id == session_id).delete(synchronize_session=False)
        self._delete_search_docs(db, session_id=session_id)
        db.commit()
        logger.info("Deleted session %s", session_id)

    def delete_user(self, db: Session, user_id: str) -> None:
        db.query(Memory).filter(Memory.user_id == user_id).delete(synchronize_session=False)
        db.query(Turn).filter(Turn.user_id == user_id).delete(synchronize_session=False)
        self._delete_search_docs(db, user_id=user_id)
        db.commit()
        logger.info("Deleted user %s", user_id)

    def _delete_search_docs(
        self,
        db: Session,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        q = db.query(SearchDocument)
        if session_id:
            q = q.filter(SearchDocument.session_id == session_id)
        if user_id:
            q = q.filter(SearchDocument.user_id == user_id)
        doc_ids = [d.id for d in q.all()]
        for doc_id in doc_ids:
            db.execute(text("DELETE FROM search_fts WHERE doc_id = :doc_id"), {"doc_id": doc_id})
        q.delete(synchronize_session=False)
