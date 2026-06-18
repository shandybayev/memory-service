"""Supersession and contradiction handling."""

from tests.conftest import post_turn


def test_employment_supersession(client):
    post_turn(
        client,
        session_id="sess-job",
        user_id="user-job",
        messages=[{"role": "user", "content": "I work at Stripe."}],
    )
    post_turn(
        client,
        session_id="sess-job",
        user_id="user-job",
        messages=[{"role": "user", "content": "I just joined Notion."}],
    )

    memories = client.get("/users/user-job/memories").json()
    companies = [m for m in memories if m["key"] == "employment.company"]
    active = [m for m in companies if m["active"]]
    inactive = [m for m in companies if not m["active"]]

    assert len(active) == 1
    assert "Notion" in active[0]["value"]
    assert len(inactive) >= 1
    assert any("Stripe" in m["value"] for m in inactive)
    assert active[0]["supersedes"] in [m["id"] for m in inactive]

    recall = client.post(
        "/recall",
        json={
            "query": "Where does the user work?",
            "session_id": "sess-job",
            "user_id": "user-job",
            "max_tokens": 512,
        },
    ).json()
    assert "Notion" in recall["context"]
    assert "Stripe" not in recall["context"]

    search = client.post(
        "/search",
        json={
            "query": "Stripe",
            "session_id": "sess-job",
            "user_id": "user-job",
            "limit": 10,
        },
    ).json()
    assert not any("Stripe" in r["content"] for r in search["results"])
