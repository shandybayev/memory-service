"""Extraction pipeline: rules + optional LLM."""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from src.api.schemas import MessageSchema
from src.db.models import Memory, Turn, utcnow
from src.services.extraction.llm import LLMExtractor
from src.services.extraction.rules import RuleExtractor
from src.services.extraction.types import ExtractedMemory

logger = logging.getLogger(__name__)


class ExtractionPipeline:
    def __init__(self) -> None:
        self.rules = RuleExtractor()
        self.llm = LLMExtractor()

    def extract_from_turn(
        self,
        db: Session,
        turn: Turn,
        messages: list[MessageSchema],
    ) -> list[Memory]:
        """Extract memories, apply supersession, persist and index."""
        if not turn.user_id:
            logger.info("Skipping extraction for anonymous turn %s", turn.id)
            return []

        candidates: list[ExtractedMemory] = []
        candidates.extend(self.rules.extract(messages))

        llm_candidates = self.llm.extract(messages)
        candidates = self._merge_candidates(candidates, llm_candidates)

        persisted: list[Memory] = []
        for item in candidates:
            result = self._persist_with_supersession(db, turn, item)
            if result:
                persisted.extend(result)

        db.flush()
        logger.info("Extracted %d memory records from turn %s", len(persisted), turn.id)
        return persisted

    def _merge_candidates(
        self, rules: list[ExtractedMemory], llm: list[ExtractedMemory]
    ) -> list[ExtractedMemory]:
        by_key: dict[str, ExtractedMemory] = {}
        for item in rules:
            by_key[item.key] = item
        for item in llm:
            if item.key not in by_key or item.confidence > by_key[item.key].confidence:
                by_key[item.key] = item
        return list(by_key.values())

    def _persist_with_supersession(
        self, db: Session, turn: Turn, item: ExtractedMemory
    ) -> list[Memory]:
        assert turn.user_id is not None
        now = utcnow()
        affected: list[Memory] = []

        existing = (
            db.query(Memory)
            .filter(
                Memory.user_id == turn.user_id,
                Memory.key == item.key,
                Memory.active.is_(True),
            )
            .order_by(Memory.updated_at.desc())
            .first()
        )

        if existing and self._same_value(existing.value, item.value):
            existing.updated_at = now
            existing.confidence = max(existing.confidence, item.confidence)
            existing.source_turn = turn.id
            existing.source_session = turn.session_id
            return [existing]

        memory = Memory(
            user_id=turn.user_id,
            type=item.type,
            key=item.key,
            value=item.value,
            confidence=item.confidence,
            source_session=turn.session_id,
            source_turn=turn.id,
            created_at=now,
            updated_at=now,
            active=True,
            search_text=item.search_text,
        )
        db.add(memory)
        db.flush()

        if existing and not self._same_value(existing.value, item.value):
            existing.active = False
            existing.updated_at = now
            memory.supersedes = existing.id
            affected.append(existing)
            logger.info(
                "Memory %s supersedes %s for key %s",
                memory.id,
                existing.id,
                item.key,
            )

        affected.append(memory)
        return affected

    @staticmethod
    def _same_value(a: str, b: str) -> bool:
        return re.sub(r"\s+", " ", a.strip().lower()) == re.sub(r"\s+", " ", b.strip().lower())
