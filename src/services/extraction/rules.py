"""Deterministic rule-based memory extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.api.schemas import MessageSchema
from src.db.models import MemoryType
from src.services.extraction.types import ExtractedMemory

# Patterns: (regex, memory_type, key_template, confidence)
FACT_PATTERNS: list[tuple[re.Pattern[str], MemoryType, str, float]] = [
    (
        re.compile(
            r"\b(?:i(?:'m| am)?\s+(?:now\s+)?(?:working|employed)\s+at|i\s+work\s+at|i\s+just\s+joined)\s+(.+?)(?:[.!?,]|$)",
            re.I,
        ),
        MemoryType.fact,
        "employment.company",
        0.92,
    ),
    (
        re.compile(
            r"\b(?:i\s+(?:just\s+)?moved\s+to|i\s+live\s+in|i(?:'m| am)\s+based\s+in|i\s+relocated\s+to)\s+(.+?)(?:[.!?,]|$)",
            re.I,
        ),
        MemoryType.fact,
        "location.residence",
        0.9,
    ),
    (
        re.compile(
            r"\b(?:i(?:'m| am)\s+from|i\s+used\s+to\s+live\s+in|i\s+moved\s+from)\s+(.+?)(?:[.!?,]|$)",
            re.I,
        ),
        MemoryType.fact,
        "location.previous",
        0.85,
    ),
    (
        re.compile(r"\bmy\s+(?:wife|husband|partner)(?:'s name)?\s+is\s+(.+?)(?:[.!?,]|$)", re.I),
        MemoryType.fact,
        "family.partner",
        0.88,
    ),
    (
        re.compile(r"\bmy\s+(?:dog|cat|pet)(?:'s name)?\s+is\s+(.+?)(?:[.!?,]|$)", re.I),
        MemoryType.fact,
        "pets.name",
        0.88,
    ),
    (
        re.compile(r"\bmy\s+name\s+is\s+(.+?)(?:[.!?,]|$)", re.I),
        MemoryType.fact,
        "identity.name",
        0.95,
    ),
]

PREFERENCE_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"\bi\s+prefer\s+(.+?)(?:[.!?,]|$)", re.I), "preference.general", 0.85),
    (re.compile(r"\bi\s+(?:really\s+)?(?:love|like)\s+(.+?)(?:[.!?,]|$)", re.I), "preference.likes", 0.8),
    (re.compile(r"\bi\s+(?:really\s+)?(?:hate|dislike|don'?t\s+like)\s+(.+?)(?:[.!?,]|$)", re.I), "preference.dislikes", 0.82),
]

OPINION_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"\bi\s+think\s+(.+?)(?:[.!?,]|$)", re.I), "opinion.general", 0.75),
    (re.compile(r"\bin\s+my\s+opinion[,]?\s+(.+?)(?:[.!?,]|$)", re.I), "opinion.general", 0.78),
    (re.compile(r"\bi\s+believe\s+(.+?)(?:[.!?,]|$)", re.I), "opinion.general", 0.76),
]

CORRECTION_PREFIXES = ("actually", "correction:", "i meant", "no wait", "sorry,")


class RuleExtractor:
    def extract(self, messages: list[MessageSchema]) -> list[ExtractedMemory]:
        results: list[ExtractedMemory] = []
        user_texts = [m.content for m in messages if m.role == "user"]
        combined = " ".join(user_texts)

        for text in user_texts:
            corrected = self._strip_correction_prefix(text)
            results.extend(self._match_patterns(corrected, is_correction=text != corrected))

        results.extend(self._extract_move_events(combined))
        results.extend(self._extract_employment_change(combined))
        return self._dedupe(results)

    def _strip_correction_prefix(self, text: str) -> str:
        lowered = text.strip().lower()
        for prefix in CORRECTION_PREFIXES:
            if lowered.startswith(prefix):
                return text.strip()[len(prefix) :].lstrip(" ,:-")
        return text

    def _match_patterns(self, text: str, is_correction: bool) -> list[ExtractedMemory]:
        found: list[ExtractedMemory] = []
        boost = 0.05 if is_correction else 0.0

        for pattern, mem_type, key, conf in FACT_PATTERNS:
            match = pattern.search(text)
            if match:
                value = self._clean_capture(match.group(1))
                if value:
                    found.append(
                        ExtractedMemory(
                            type=mem_type,
                            key=key,
                            value=value,
                            confidence=min(conf + boost, 0.99),
                            search_text=f"{key} {value} {text}",
                        )
                    )

        for pattern, key, conf in PREFERENCE_PATTERNS:
            match = pattern.search(text)
            if match:
                value = self._clean_capture(match.group(1))
                if value:
                    found.append(
                        ExtractedMemory(
                            type=MemoryType.preference,
                            key=key,
                            value=value,
                            confidence=min(conf + boost, 0.99),
                            search_text=f"preference {value} {text}",
                        )
                    )

        for pattern, key, conf in OPINION_PATTERNS:
            match = pattern.search(text)
            if match:
                value = self._clean_capture(match.group(1))
                if value:
                    found.append(
                        ExtractedMemory(
                            type=MemoryType.opinion,
                            key=key,
                            value=value,
                            confidence=min(conf + boost, 0.99),
                            search_text=f"opinion {value} {text}",
                        )
                    )
        return found

    def _extract_move_events(self, combined: str) -> list[ExtractedMemory]:
        pattern = re.compile(
            r"moved\s+(?:from\s+)?(.+?)\s+to\s+(.+?)(?:[.!?,]|$)",
            re.I,
        )
        match = pattern.search(combined)
        if not match:
            return []
        origin = self._clean_capture(match.group(1))
        dest = self._clean_capture(match.group(2))
        if not dest:
            return []
        items = [
            ExtractedMemory(
                type=MemoryType.fact,
                key="location.residence",
                value=dest,
                confidence=0.93,
                search_text=f"location residence {dest} moved from {origin}",
            ),
            ExtractedMemory(
                type=MemoryType.event,
                key="location.move",
                value=f"moved from {origin} to {dest}" if origin else f"moved to {dest}",
                confidence=0.9,
                search_text=f"move {origin} {dest}",
            ),
        ]
        if origin:
            items.append(
                ExtractedMemory(
                    type=MemoryType.fact,
                    key="location.previous",
                    value=origin,
                    confidence=0.88,
                    search_text=f"previous location {origin}",
                )
            )
        return items

    def _extract_employment_change(self, combined: str) -> list[ExtractedMemory]:
        pattern = re.compile(
            r"(?:used\s+to\s+work\s+at|previously\s+(?:worked|employed)\s+at)\s+(.+?)"
            r".{0,80}?(?:now|currently|just)\s+(?:work\s+at|joined)\s+(.+?)(?:[.!?,]|$)",
            re.I | re.S,
        )
        match = pattern.search(combined)
        if not match:
            return []
        old_co = self._clean_capture(match.group(1))
        new_co = self._clean_capture(match.group(2))
        return [
            ExtractedMemory(
                type=MemoryType.fact,
                key="employment.company",
                value=new_co,
                confidence=0.94,
                search_text=f"employment {new_co} formerly {old_co}",
            ),
            ExtractedMemory(
                type=MemoryType.event,
                key="employment.change",
                value=f"changed jobs from {old_co} to {new_co}",
                confidence=0.9,
                search_text=f"job change {old_co} {new_co}",
            ),
        ]

    @staticmethod
    def _clean_capture(value: str) -> str:
        value = value.strip().strip("\"'")
        value = re.sub(r"\s+as\s+a\s+.+$", "", value, flags=re.I)
        value = re.sub(r"\s+last\s+week$", "", value, flags=re.I)
        value = re.sub(r"\s+", " ", value)
        return value[:500]

    @staticmethod
    def _dedupe(items: list[ExtractedMemory]) -> list[ExtractedMemory]:
        seen: dict[str, ExtractedMemory] = {}
        for item in items:
            k = f"{item.type}:{item.key}:{item.value.lower()}"
            if k not in seen or item.confidence > seen[k].confidence:
                seen[k] = item
        return list(seen.values())
