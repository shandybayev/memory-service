"""SQLAlchemy ORM models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class MemoryType(str, enum.Enum):
    fact = "fact"
    preference = "preference"
    opinion = "opinion"
    event = "event"


class Base(DeclarativeBase):
    pass


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(String(255), index=True)
    user_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    messages: Mapped[list] = mapped_column(JSON, default=list)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    memories: Mapped[list["Memory"]] = relationship(back_populates="turn")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    type: Mapped[MemoryType] = mapped_column(Enum(MemoryType), index=True)
    key: Mapped[str] = mapped_column(String(255), index=True)
    value: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    source_session: Mapped[str] = mapped_column(String(255), index=True)
    source_turn: Mapped[str] = mapped_column(String(36), ForeignKey("turns.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    supersedes: Mapped[str | None] = mapped_column(String(36), ForeignKey("memories.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    search_text: Mapped[str] = mapped_column(Text, default="")

    turn: Mapped[Turn] = relationship(back_populates="memories")


Index("ix_memories_user_key_active", Memory.user_id, Memory.key, Memory.active)


class SearchDocument(Base):
    """Unified search index for hybrid retrieval over memories and turn snippets."""

    __tablename__ = "search_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    doc_type: Mapped[str] = mapped_column(String(32), index=True)  # memory | turn
    ref_id: Mapped[str] = mapped_column(String(36), index=True)
    session_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
