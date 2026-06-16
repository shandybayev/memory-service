"""Reciprocal rank fusion for hybrid scores."""

from __future__ import annotations

from collections import defaultdict


def reciprocal_rank_fusion(
    ranked_lists: list[list[tuple[str, float]]],
    k: int = 60,
) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for ranked in ranked_lists:
        for rank, (doc_id, _score) in enumerate(ranked, start=1):
            scores[doc_id] += 1.0 / (k + rank)
    return dict(scores)
