import pytest

from jev.claude_client import FALLBACK_BETA, REFUSAL_TEXT, TRUNCATED_NOTE, ClaudeClient
from jev.config import ConfigError
from tests.fakes import FakeAnthropic, make_response, text_block

MESSAGES = [{"role": "user", "content": "안녕"}]


def test_ask_builds_request_from_config():
    fake = FakeAnthropic(make_response([text_block("안"), text_block("녕")]))
    client = ClaudeClient(fake, model="test-model", max_tokens=123)
    reply = client.ask(MESSAGES, effort="low")
    assert reply.text == "안녕"
    assert not reply.refused
    (call,) = fake.create_calls
    assert call["model"] == "test-model"
    assert call["max_tokens"] == 123
    assert call["output_config"] == {"effort": "low"}
    assert call["betas"] == [FALLBACK_BETA]
    assert call["fallbacks"] == "default"
    assert call["messages"] is MESSAGES


def test_model_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("JEV_MODEL", "env-model")
    fake = FakeAnthropic(make_response([text_block("x")]))
    ClaudeClient(fake).ask(MESSAGES, effort="low")
    assert fake.create_calls[0]["model"] == "env-model"


def test_missing_model_is_config_error():
    fake = FakeAnthropic(make_response([]))
    with pytest.raises(ConfigError, match="JEV_MODEL"):
        ClaudeClient(fake).ask(MESSAGES, effort="low")
    assert fake.create_calls == []


def test_thinking_blocks_are_kept_but_not_shown():
    thinking = type("B", (), {"type": "thinking", "thinking": ""})()
    fake = FakeAnthropic(make_response([thinking, text_block("답")]))
    reply = ClaudeClient(fake, model="m").ask(MESSAGES, effort="high")
    assert reply.text == "답"
    assert reply.content[0] is thinking


def test_refusal():
    fake = FakeAnthropic(make_response([], stop_reason="refusal"))
    reply = ClaudeClient(fake, model="m").ask(MESSAGES, effort="low")
    assert reply.refused
    assert reply.text == REFUSAL_TEXT


def test_max_tokens_note():
    fake = FakeAnthropic(make_response([text_block("길다")], stop_reason="max_tokens"))
    reply = ClaudeClient(fake, model="m").ask(MESSAGES, effort="low")
    assert reply.text == "길다" + TRUNCATED_NOTE


def test_ask_stream_forwards_chunks_and_returns_final():
    fake = FakeAnthropic(make_response([text_block("안녕하세요")]), chunks=["안녕", "하세요"])
    seen = []
    reply = ClaudeClient(fake, model="m").ask_stream(MESSAGES, effort="medium", on_text=seen.append)
    assert seen == ["안녕", "하세요"]
    assert reply.text == "안녕하세요"
    assert fake.create_calls == []
    (call,) = fake.stream_calls
    assert call["output_config"] == {"effort": "medium"}
    assert call["fallbacks"] == "default"


def test_ask_stream_refusal_mid_stream():
    fake = FakeAnthropic(
        make_response([text_block("부분")], stop_reason="refusal"), chunks=["부분"]
    )
    seen = []
    reply = ClaudeClient(fake, model="m").ask_stream(MESSAGES, effort="low", on_text=seen.append)
    assert seen == ["부분"]
    assert reply.refused
