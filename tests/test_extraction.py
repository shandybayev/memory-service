"""Extraction pipeline tests (deterministic path + LLM parsing)."""

import pytest

from src.api.schemas import MessageSchema
from src.core.config import get_settings
from src.db.models import MemoryType
from src.services.extraction.llm import LLMExtractor
from src.services.extraction.rules import RuleExtractor


def test_rule_extractor_berlin_move():
    messages = [MessageSchema(role="user", content="I just moved from NYC to Berlin.")]
    results = RuleExtractor().extract(messages)
    keys = {r.key for r in results}
    assert "location.residence" in keys
    residence = next(r for r in results if r.key == "location.residence")
    assert "Berlin" in residence.value


@pytest.mark.parametrize(
    ("content", "expected_key", "expected_value"),
    [
        ("I joined Stripe.", "employment.company", "Stripe"),
        ("I started at Figma.", "employment.company", "Figma"),
        ("I work at Google.", "employment.company", "Google"),
        ("I'm working at Meta.", "employment.company", "Meta"),
        ("I switched to Notion.", "employment.company", "Notion"),
        ("I relocated to Austin.", "location.residence", "Austin"),
        ("I moved to Seattle.", "location.residence", "Seattle"),
        ("I currently live in Boston.", "location.residence", "Boston"),
        ("I now live in Denver.", "location.residence", "Denver"),
        ("I transferred to Berlin.", "location.residence", "Berlin"),
        (
            "I just moved to Berlin from NYC last month.",
            "location.residence",
            "Berlin",
        ),
        ("I'm based in Chicago.", "location.residence", "Chicago"),
        ("I'm now at Airbnb.", "employment.company", "Airbnb"),
        ("I'm currently at Spotify.", "employment.company", "Spotify"),
        ("I moved over to Vancouver.", "location.residence", "Vancouver"),
        ("I'm located in Dallas.", "location.residence", "Dallas"),
        ("Working at Netflix.", "employment.company", "Netflix"),
    ],
)
def test_rule_extractor_common_patterns(content, expected_key, expected_value):
    messages = [MessageSchema(role="user", content=content)]
    results = RuleExtractor().extract(messages)
    match = next((r for r in results if r.key == expected_key), None)
    assert match is not None, f"No {expected_key} for: {content}"
    assert expected_value.lower() in match.value.lower()


def test_llm_extractor_returns_empty_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        messages = [MessageSchema(role="user", content="I live in Paris.")]
        assert LLMExtractor().extract(messages) == []
    finally:
        get_settings.cache_clear()


def test_llm_extractor_parses_memories_json_object(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_settings.cache_clear()

    class _FakeMessage:
        content = (
            '{"memories": [{"type": "fact", "key": "location.residence", '
            '"value": "Paris", "confidence": 0.9}]}'
        )

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]

    class _FakeCompletions:
        @staticmethod
        def create(**_kwargs):
            return _FakeResponse()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setattr("openai.OpenAI", lambda api_key: _FakeClient())

    try:
        messages = [MessageSchema(role="user", content="I live in Paris.")]
        results = LLMExtractor().extract(messages)
        assert len(results) == 1
        assert results[0].type == MemoryType.fact
        assert results[0].key == "location.residence"
        assert results[0].value == "Paris"
    finally:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        get_settings.cache_clear()


def test_llm_extractor_returns_empty_on_api_failure(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_settings.cache_clear()

    def _raise(*_args, **_kwargs):
        raise RuntimeError("API unavailable")

    monkeypatch.setattr("openai.OpenAI", _raise)

    try:
        messages = [MessageSchema(role="user", content="I live in Paris.")]
        assert LLMExtractor().extract(messages) == []
    finally:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        get_settings.cache_clear()


def test_llm_parse_response_invalid_json_returns_empty():
    assert LLMExtractor.parse_response_content("{not json") == []


def test_llm_parse_response_missing_memories_returns_empty():
    assert LLMExtractor.parse_response_content('{"items": []}') == []


def test_pipeline_uses_rules_only_without_api_key(monkeypatch, client):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        response = client.post(
            "/turns",
            json={
                "session_id": "sess-rules-only",
                "user_id": "user-rules-only",
                "messages": [{"role": "user", "content": "I work at Stripe."}],
            },
        )
        assert response.status_code == 201
        memories = client.get("/users/user-rules-only/memories").json()
        assert any(m["key"] == "employment.company" and m["active"] for m in memories)
    finally:
        get_settings.cache_clear()


def test_pipeline_uses_rules_when_llm_fails(monkeypatch, client):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_settings.cache_clear()

    def _raise(*_args, **_kwargs):
        raise RuntimeError("API unavailable")

    monkeypatch.setattr("openai.OpenAI", _raise)

    try:
        response = client.post(
            "/turns",
            json={
                "session_id": "sess-llm-fail",
                "user_id": "user-llm-fail",
                "messages": [{"role": "user", "content": "I joined Notion."}],
            },
        )
        assert response.status_code == 201
        memories = client.get("/users/user-llm-fail/memories").json()
        assert any(m["key"] == "employment.company" and "Notion" in m["value"] for m in memories)
    finally:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        get_settings.cache_clear()
