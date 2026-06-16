"""Index memories and turns for hybrid retrieval."""

from __future__ import annotations

import logging

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.schemas import MessageSchema
from src.db.models import Memory, SearchDocument, Turn, new_id
from src.services.retrieval.semantic import SemanticEncoder

logger = logging.getLogger(__name__)


class IndexService:
    def __init__(self) -> None:
        self.encoder = SemanticEncoder()

    def index_turn(self, db: Session, turn: Turn, messages: list[MessageSchema]) -> None:
        snippets = self._turn_snippets(messages)
        for snippet in snippets:
            self._upsert_document(
                db,
                doc_type="turn",
                ref_id=turn.id,
                session_id=turn.session_id,
                user_id=turn.user_id,
                content=snippet,
                timestamp=turn.timestamp,
                metadata={"turn_id": turn.id},
            )

    def index_memory(self, db: Session, memory: Memory) -> None:
        content = f"{memory.type.value}: {memory.key} = {memory.value}"
        if not memory.active:
            content = f"[inactive] {content}"
        self._upsert_document(
            db,
            doc_type="memory",
            ref_id=memory.id,
            session_id=memory.source_session,
            user_id=memory.user_id,
            content=content,
            timestamp=memory.updated_at,
            metadata={
                "memory_id": memory.id,
                "memory_type": memory.type.value,
                "key": memory.key,
                "active": memory.active,
                "turn_id": memory.source_turn,
            },
        )

    def _upsert_document(
        self,
        db: Session,
        *,
        doc_type: str,
        ref_id: str,
        session_id: str | None,
        user_id: str | None,
        content: str,
        timestamp,
        metadata: dict,
    ) -> None:
        existing = (
            db.query(SearchDocument)
            .filter(SearchDocument.doc_type == doc_type, SearchDocument.ref_id == ref_id)
            .first()
            if doc_type == "memory"
            else (
                db.query(SearchDocument)
                .filter(
                    SearchDocument.doc_type == doc_type,
                    SearchDocument.ref_id == ref_id,
                    SearchDocument.content == content,
                )
                .first()
            )
        )
        embedding = self.encoder.encode_single(content)
        if existing:
            existing.content = content
            existing.timestamp = timestamp
            existing.metadata_ = metadata
            existing.embedding = embedding
            doc_id = existing.id
        else:
            doc = SearchDocument(
                id=new_id(),
                doc_type=doc_type,
                ref_id=ref_id,
                session_id=session_id,
                user_id=user_id,
                content=content,
                timestamp=timestamp,
                metadata_=metadata,
                embedding=embedding,
            )
            db.add(doc)
            db.flush()
            doc_id = doc.id

        db.execute(
            text("DELETE FROM search_fts WHERE doc_id = :doc_id"),
            {"doc_id": doc_id},
        )
        db.execute(
            text("INSERT INTO search_fts(doc_id, content) VALUES (:doc_id, :content)"),
            {"doc_id": doc_id, "content": content},
        )

    @staticmethod
    def _turn_snippets(messages: list[MessageSchema]) -> list[str]:
        snippets: list[str] = []
        for msg in messages:
            prefix = msg.name if msg.role == "tool" and msg.name else msg.role
            snippets.append(f"{prefix}: {msg.content}")
        if len(snippets) > 1:
            snippets.append(" | ".join(snippets))
        return snippets
