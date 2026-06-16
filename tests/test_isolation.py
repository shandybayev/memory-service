"""Isolation between users and sessions."""

from tests.conftest import post_turn


def test_concurrent_sessions_do_not_bleed(client):
    post_turn(
        client,
        session_id="sess-a",
        user_id="user-a",
        messages=[{"role": "user", "content": "I live in Tokyo."}],
    )
    post_turn(
        client,
        session_id="sess-b",
        user_id="user-b",
        messages=[{"role": "user", "content": "I live in Madrid."}],
    )

    recall_a = client.post(
        "/recall",
        json={
            "query": "Where does the user live?",
            "session_id": "sess-a",
            "user_id": "user-a",
            "max_tokens": 512,
        },
    ).json()
    recall_b = client.post(
        "/recall",
        json={
            "query": "Where does the user live?",
            "session_id": "sess-b",
            "user_id": "user-b",
            "max_tokens": 512,
        },
    ).json()

    assert "Tokyo" in recall_a["context"]
    assert "Madrid" not in recall_a["context"]
    assert "Madrid" in recall_b["context"]
    assert "Tokyo" not in recall_b["context"]
