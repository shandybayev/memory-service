"""Malformed input and edge cases."""

import json

from tests.conftest import post_turn


def test_bad_json_returns_422(client):
    response = client.post(
        "/turns",
        content=b"{not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_missing_messages_returns_422(client):
    response = client.post(
        "/turns",
        json={"session_id": "s1", "user_id": "u1", "messages": []},
    )
    assert response.status_code == 422


def test_unicode_content(client):
    response = client.post(
        "/turns",
        json={
            "session_id": "sess-unicode",
            "user_id": "user-unicode",
            "messages": [
                {"role": "user", "content": "I moved to München 🎉 — formerly Zürich."},
                {"role": "assistant", "content": "Willkommen!"},
            ],
            "timestamp": "2025-02-01T12:00:00Z",
        },
    )
    assert response.status_code == 201


def test_optional_fields_missing(client):
    response = client.post(
        "/turns",
        json={
            "session_id": "sess-min",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 201


def test_tool_messages(client):
    response = client.post(
        "/turns",
        json={
            "session_id": "sess-tool",
            "user_id": "user-tool",
            "messages": [
                {"role": "user", "content": "What's the weather?"},
                {"role": "tool", "name": "weather_api", "content": "72F sunny"},
                {"role": "assistant", "content": "It is sunny."},
            ],
        },
    )
    assert response.status_code == 201


def test_search_requires_scope(client):
    response = client.post(
        "/search",
        json={"query": "anything", "limit": 5},
    )
    assert response.status_code == 422


def test_search_no_alphanumeric_tokens_returns_422(client):
    response = client.post(
        "/search",
        json={"query": "!!!", "session_id": "s1", "limit": 5},
    )
    assert response.status_code == 422


def test_search_fts_poison_query_never_500(client):
    """Malformed FTS syntax must not crash the service."""
    response = client.post(
        "/search",
        json={"query": '" OR "', "session_id": "s1", "user_id": "u1", "limit": 5},
    )
    assert response.status_code != 500
    assert response.status_code in (200, 422)


def test_recall_fts_poison_query_never_500(client):
    post_turn(client, session_id="s-poison", user_id="u-poison")
    response = client.post(
        "/recall",
        json={
            "query": '" OR "',
            "session_id": "s-poison",
            "user_id": "u-poison",
            "max_tokens": 512,
        },
    )
    assert response.status_code != 500
    assert response.status_code == 200


def test_oversized_payload_returns_413(client, monkeypatch):
    monkeypatch.setenv("MAX_TURN_PAYLOAD_BYTES", "200")
    from src.core.config import get_settings

    get_settings.cache_clear()

    big = "x" * 500
    response = client.post(
        "/turns",
        json={
            "session_id": "sess-big",
            "user_id": "user-big",
            "messages": [{"role": "user", "content": big}],
        },
    )
    assert response.status_code == 413
    get_settings.cache_clear()
