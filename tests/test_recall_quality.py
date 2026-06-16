"""Recall quality fixture evaluation."""

from fixtures.recall_quality import RECALL_FIXTURES
from tests.conftest import post_turn


def _score_probe(context: str, probe: dict) -> tuple[int, int]:
    context_lower = context.lower()
    expected = probe.get("expected_facts", [])
    hits = sum(1 for fact in expected if fact.lower() in context_lower)
    for bad in probe.get("must_not_include", []):
        assert bad.lower() not in context_lower
    return hits, len(expected)


def test_recall_quality_fixtures(client):
    total_expected = 0
    total_hits = 0

    for fixture in RECALL_FIXTURES:
        for turn in fixture["turns"]:
            post_turn(
                client,
                session_id=fixture["session_id"],
                user_id=fixture["user_id"],
                messages=turn["messages"],
            )

        for probe in fixture["probes"]:
            response = client.post(
                "/recall",
                json={
                    "query": probe["query"],
                    "session_id": fixture["session_id"],
                    "user_id": fixture["user_id"],
                    "max_tokens": 1024,
                },
            )
            assert response.status_code == 200
            context = response.json()["context"]
            hits, expected = _score_probe(context, probe)
            total_hits += hits
            total_expected += expected

    quality = total_hits / total_expected if total_expected else 1.0
    assert quality >= 0.75, f"Recall quality too low: {total_hits}/{total_expected}"
