"""Cross-session user memory recall."""

from tests.conftest import post_turn


def test_recall_finds_user_memories_from_other_session(client):
    post_turn(
        client,
        session_id="sess-origin",
        user_id="user-cross",
        messages=[
            {"role": "user", "content": "I just moved from NYC to Berlin."},
            {"role": "assistant", "content": "Welcome to Berlin!"},
        ],
    )

    recall = client.post(
        "/recall",
        json={
            "query": "Where does this user live?",
            "session_id": "sess-new",
            "user_id": "user-cross",
            "max_tokens": 1024,
        },
    )
    assert recall.status_code == 200
    context = recall.json()["context"]
    assert "Berlin" in context

    search = client.post(
        "/search",
        json={
            "query": "Berlin",
            "session_id": "sess-new",
            "user_id": "user-cross",
            "limit": 5,
        },
    )
    assert search.status_code == 200
    assert any("Berlin" in r["content"] for r in search.json()["results"])
