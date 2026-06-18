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

    @staticmethod
    def parse_response_content(content: str) -> list[ExtractedMemory]:
        """Parse OpenAI json_object response into extracted memories."""
        try:
            payload = json.loads(content or "{}")
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON; using rules only")
            return []

        rows = payload if isinstance(payload, list) else payload.get("memories", [])
        if not isinstance(rows, list):
            logger.warning("LLM memories payload is not a list; using rules only")
            return []

        results: list[ExtractedMemory] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
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
            except (KeyError, ValueError, TypeError):
                continue
        return results

    def _extract_with_openai(
        self, messages: list[MessageSchema], api_key: str, model: str
    ) -> list[ExtractedMemory]:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        transcript = "\n".join(f"{m.role}: {m.content}" for m in messages)
        prompt = (
            "Extract structured memories from this conversation turn. "
            'Return a JSON object with key "memories": an array of objects. '
            "Each object must have: type (fact|preference|opinion|event), "
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
        return self.parse_response_content(content)
