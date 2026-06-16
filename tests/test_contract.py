"""Contract roundtrip tests."""

from tests.conftest import post_turn


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_turn_recall_roundtrip(client):
    post_turn(
        client,
        session_id="sess-roundtrip",
        user_id="user-roundtrip",
        messages=[
            {"role": "user", "content": "I just moved from NYC to Berlin."},
            {"role": "assistant", "content": "Berlin is great."},
        ],
    )

    recall = client.post(
        "/recall",
        json={
            "query": "Where does this user live?",
            "session_id": "sess-roundtrip",
            "user_id": "user-roundtrip",
            "max_tokens": 1024,
        },
    )
    assert recall.status_code == 200
    body = recall.json()
    assert "context" in body
    assert "citations" in body
    assert "Berlin" in body["context"]

    memories = client.get("/users/user-roundtrip/memories")
    assert memories.status_code == 200
    data = memories.json()
    assert len(data) >= 1
    assert all("type" in m and "key" in m and "value" in m for m in data)
    active_residence = [m for m in data if m["key"] == "location.residence" and m["active"]]
    assert any("Berlin" in m["value"] for m in active_residence)


def test_search_returns_structured_results(client):
    post_turn(
        client,
        user_id="user-search",
        session_id="sess-search",
        messages=[{"role": "user", "content": "I prefer hiking on weekends."}],
    )
    response = client.post(
        "/search",
        json={"query": "hiking", "session_id": "sess-search", "user_id": "user-search", "limit": 5},
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) >= 1
    assert "content" in results[0]
    assert "score" in results[0]
