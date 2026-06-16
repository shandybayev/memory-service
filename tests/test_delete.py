"""DELETE endpoint tests."""

from tests.conftest import post_turn


def test_delete_session_removes_data(client):
    post_turn(
        client,
        session_id="sess-del",
        user_id="user-del",
        messages=[{"role": "user", "content": "I live in Oslo."}],
    )

    response = client.delete("/sessions/sess-del")
    assert response.status_code == 204

    recall = client.post(
        "/recall",
        json={
            "query": "Where does the user live?",
            "session_id": "sess-del",
            "user_id": "user-del",
            "max_tokens": 512,
        },
    )
    assert recall.status_code == 200
    assert recall.json()["context"] == ""

    memories = client.get("/users/user-del/memories").json()
    assert memories == []


def test_delete_user_removes_all_user_data(client):
    post_turn(
        client,
        session_id="sess-user-del",
        user_id="user-wipe",
        messages=[{"role": "user", "content": "I work at Figma."}],
    )

    response = client.delete("/users/user-wipe")
    assert response.status_code == 204

    memories = client.get("/users/user-wipe/memories").json()
    assert memories == []

    search = client.post(
        "/search",
        json={"query": "Figma", "user_id": "user-wipe", "limit": 5},
    )
    assert search.status_code == 200
    assert search.json()["results"] == []
