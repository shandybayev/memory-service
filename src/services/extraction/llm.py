"""Optional LLM-based extraction with rule fallback."""

from __future__ import annotations

import json
import logging

from src.api.schemas import MessageSchema
from src.core.config import get_settings
from src.db.models import MemoryType
from src.services.extraction.types import ExtractedMemory

logger = logging.getLogger(__name__)


class LLMExtractor:
    def extract(self, messages: list[MessageSchema]) -> list[ExtractedMemory]:
        settings = get_settings()
        if not settings.openai_api_key:
            return []

        try:
            return self._extract_with_openai(messages, settings.openai_api_key, settings.openai_model)
        except Exception:
            logger.exception("LLM extraction failed; using rules only")
            return []

    def _extract_with_openai(
        self, messages: list[MessageSchema], api_key: str, model: str
    ) -> list[ExtractedMemory]:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        transcript = "\n".join(f"{m.role}: {m.content}" for m in messages)
        prompt = (
            "Extract structured memories from this conversation turn. "
            "Return JSON array of objects with keys: type (fact|preference|opinion|event), "
            "key (normalized dotted key), value (short string), confidence (0-1). "
            "Only include explicit or strongly implied user information."
        )
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": transcript},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        payload = json.loads(content)
        rows = payload if isinstance(payload, list) else payload.get("memories", [])
        results: list[ExtractedMemory] = []
        for row in rows:
            try:
                mem_type = MemoryType(row["type"])
                value = str(row["value"]).strip()
                key = str(row["key"]).strip()
                if not value or not key:
                    continue
                results.append(
                    ExtractedMemory(
                        type=mem_type,
                        key=key,
                        value=value,
                        confidence=float(row.get("confidence", 0.7)),
                        search_text=f"{key} {value}",
                    )
                )
            except (KeyError, ValueError):
                continue
        return results
