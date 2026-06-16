"""Assemble recall context under token budget."""

from __future__ import annotations

from src.api.schemas import CitationSchema, RecallResponse
from src.services.retrieval.hybrid import RetrievalHit


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class ContextFormatter:
    def build_recall(
        self,
        query: str,
        hits: list[RetrievalHit],
        max_tokens: int,
    ) -> RecallResponse:
        if not hits:
            return RecallResponse(context="", citations=[])

        facts = [
            h
            for h in hits
            if h.metadata.get("memory_type") == "fact" or h.metadata.get("source") == "active_memory"
        ]
        preferences = [h for h in hits if h.metadata.get("memory_type") in ("preference", "opinion")]
        events = [h for h in hits if h.metadata.get("memory_type") == "event"]
        conversational = [h for h in hits if h not in facts + preferences + events]

        ordered = (
            self._dedupe_content(facts)
            + self._dedupe_content(preferences)
            + self._dedupe_content(events)
            + self._dedupe_content(conversational)
        )

        sections: list[str] = []
        citations: list[CitationSchema] = []
        used_tokens = 0
        header = "## Retrieved memory context\n"
        used_tokens += estimate_tokens(header)
        sections.append(header.strip())

        for hit in ordered:
            line = self._format_hit(hit)
            tokens = estimate_tokens(line)
            if used_tokens + tokens > max_tokens:
                break
            sections.append(line)
            used_tokens += tokens
            if hit.turn_id:
                citations.append(
                    CitationSchema(
                        turn_id=hit.turn_id,
                        score=round(hit.score, 4),
                        snippet=hit.content[:240],
                    )
                )

        context = "\n".join(sections).strip()
        if context == "## Retrieved memory context":
            context = ""
        return RecallResponse(context=context, citations=citations)

    def _format_hit(self, hit: RetrievalHit) -> str:
        meta = hit.metadata or {}
        if meta.get("source") == "active_memory" or meta.get("memory_type"):
            key = meta.get("key", "")
            value = hit.content.split("=", 1)[-1].strip()
            return f"- [{meta.get('memory_type', 'memory')}] {key}: {value}"
        return f"- [conversation] {hit.content}"

    def _dedupe_content(self, hits: list[RetrievalHit]) -> list[RetrievalHit]:
        seen: set[str] = set()
        unique: list[RetrievalHit] = []
        for hit in hits:
            key = hit.content.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(hit)
        return unique
