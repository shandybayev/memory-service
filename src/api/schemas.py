"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class MessageSchema(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str
    name: str | None = None

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if v is None:
            raise ValueError("content is required")
        return v


class TurnCreateRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=255)
    user_id: str | None = Field(default=None, max_length=255)
    messages: list[MessageSchema] = Field(..., min_length=1)
    timestamp: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TurnCreateResponse(BaseModel):
    id: str


class RecallRequest(BaseModel):
    query: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    user_id: str | None = None
    max_tokens: int = Field(default=1024, ge=64, le=8192)


class CitationSchema(BaseModel):
    turn_id: str
    score: float
    snippet: str


class RecallResponse(BaseModel):
    context: str
    citations: list[CitationSchema]


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    session_id: str | None = None
    user_id: str | None = None
    limit: int = Field(default=10, ge=1, le=100)


class SearchResultSchema(BaseModel):
    content: str
    score: float
    session_id: str
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    results: list[SearchResultSchema]


class MemorySchema(BaseModel):
    id: str
    type: Literal["fact", "preference", "opinion", "event"]
    key: str
    value: str
    confidence: float
    source_session: str
    source_turn: str
    created_at: datetime
    updated_at: datetime
    supersedes: str | None
    active: bool
