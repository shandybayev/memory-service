"""Shared extraction types."""

from dataclasses import dataclass

from src.db.models import MemoryType


@dataclass
class ExtractedMemory:
    type: MemoryType
    key: str
    value: str
    confidence: float
    search_text: str
