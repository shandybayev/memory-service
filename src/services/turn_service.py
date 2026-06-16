"""Turn ingestion orchestration."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from src.api.schemas import MessageSchema, TurnCreateRequest
from src.db.models import Turn, utcnow
from src.services.extraction.pipeline import ExtractionPipeline
from src.services.indexing import IndexService

logger = logging.getLogger(__name__)


class TurnService:
    def __init__(self) -> None:
        self.extractor = ExtractionPipeline()
        self.indexer = IndexService()

    def create_turn(self, db: Session, payload: TurnCreateRequest) -> Turn:
        turn = Turn(
            session_id=payload.session_id,
            user_id=payload.user_id,
            messages=[m.model_dump() for m in payload.messages],
            timestamp=payload.timestamp or utcnow(),
            metadata_=payload.metadata,
        )
        db.add(turn)
        db.flush()

        memories = self.extractor.extract_from_turn(db, turn, payload.messages)
        self.indexer.index_turn(db, turn, payload.messages)
        for memory in memories:
            self.indexer.index_memory(db, memory)

        db.commit()
        db.refresh(turn)
        logger.info("Persisted turn %s for session %s", turn.id, turn.session_id)
        return turn
