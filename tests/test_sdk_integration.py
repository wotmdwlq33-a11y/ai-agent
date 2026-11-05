"""실제 anthropic SDK를 가짜 HTTP 전송 계층에 연결해 요청 모양과 응답 해석을 확인한다.

네트워크는 쓰지 않는다. SDK가 우리 요청 인자(betas, fallbacks, output_config 등)를 받아들이고,
일반 응답과 SSE 스트림을 ClaudeReply로 제대로 바꾸는지 본다.
"""

from __future__ import annotations

import json

import anthropic
import httpx2
import pytest

from jev.claude_client import FALLBACK_BETA, TRUNCATED_NOTE, ClaudeClient
from jev.memory import ConversationStore

MESSAGES = [{"role": "user", "content": "안녕"}]


def _message(content, stop_reason="end_turn"):
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "test-model",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 3, "output_tokens": 2},
    }


def _sse(events):
    return "".join(
        f"event: {e['type']}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n" for e in events
    )


def _stream_events(chunks, stop_reason="end_turn"):
    start = _message([], stop_reason=None)
    events = [
        {"type": "message_start", "message": start},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    ]
    events += [
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": c}}
        for c in chunks
    ]
    events += [
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": len(chunks)},
        },
        {"type": "message_stop"},
    ]
    return events


class Recorder:
    def __init__(self, response_factory):
        self.requests: list[httpx2.Request] = []
        self._factory = response_factory

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self._factory(request)

    def body(self, i=0):
        return json.loads(self.requests[i].content)


def make_client(handler) -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key="test-key",
        base_url="https://api.example.invalid",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
        max_retries=0,
    )


def test_ask_through_real_sdk():
    rec = Recorder(
        lambda req: httpx2.Response(200, json=_message([{"type": "text", "text": "반가워요"}]))
    )
    reply = ClaudeClient(make_client(rec), model="test-model", max_tokens=100).ask(
        MESSAGES, effort="low"
    )
    assert reply.text == "반가워요"
    body = rec.body()
    assert body["model"] == "test-model"
    assert body["max_tokens"] == 100
    assert body["output_config"] == {"effort": "low"}
    assert body["fallbacks"] == "default"
    assert FALLBACK_BETA in rec.requests[0].headers["anthropic-beta"]
    assert rec.requests[0].url.path == "/v1/messages"


def test_stream_through_real_sdk_and_history_roundtrip(tmp_path):
    def handler(req):
        return httpx2.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(_stream_events(["안녕", "하세요"])).encode(),
        )

    rec = Recorder(handler)
    seen: list[str] = []
    reply = ClaudeClient(make_client(rec), model="test-model").ask_stream(
        MESSAGES, effort="medium", on_text=seen.append
    )
    assert seen == ["안녕", "하세요"]
    assert reply.text == "안녕하세요"
    assert rec.body()["stream"] is True

    # SDK가 돌려준 실제 블록 객체도 기록 파일에 저장하고 다시 읽을 수 있어야 한다
    store = ConversationStore(tmp_path / "history.json")
    history = [*MESSAGES, {"role": "assistant", "content": reply.content}]
    store.save(history)
    assert store.load()[1]["content"] == [{"type": "text", "text": "안녕하세요"}]


def test_stream_max_tokens_through_real_sdk():
    def handler(req):
        events = _stream_events(["길"], stop_reason="max_tokens")
        return httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, content=_sse(events).encode()
        )

    seen: list[str] = []
    reply = ClaudeClient(make_client(Recorder(handler)), model="m").ask_stream(
        MESSAGES, effort="low", on_text=seen.append
    )
    assert seen == ["길", TRUNCATED_NOTE]
    assert reply.text == "길" + TRUNCATED_NOTE


def test_http_errors_surface_as_sdk_errors():
    def handler(req):
        return httpx2.Response(
            429, json={"type": "error", "error": {"type": "rate_limit_error", "message": "slow"}}
        )

    client = ClaudeClient(make_client(Recorder(handler)), model="m")
    with pytest.raises(anthropic.RateLimitError):
        client.ask(MESSAGES, effort="low")


def test_stream_refusal_through_real_sdk():
    def handler(req):
        events = _stream_events(["부분"], stop_reason="refusal")
        return httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, content=_sse(events).encode()
        )

    reply = ClaudeClient(make_client(Recorder(handler)), model="m").ask_stream(
        MESSAGES, effort="low", on_text=lambda _: None
    )
    assert reply.refused
