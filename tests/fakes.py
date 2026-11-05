"""테스트용 가짜 Anthropic 클라이언트와 가짜 Claude. 실제 API를 호출하지 않는다."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from jev.claude_client import ClaudeReply


def text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def make_response(content: list[Any], stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(content=content, stop_reason=stop_reason)


class _FakeStream:
    def __init__(self, chunks: list[str], response: SimpleNamespace) -> None:
        self._chunks = chunks
        self._response = response
        self.closed = False

    def __enter__(self) -> _FakeStream:
        return self

    def __exit__(self, *exc: object) -> None:
        self.closed = True

    @property
    def text_stream(self):
        yield from self._chunks

    def get_final_message(self) -> SimpleNamespace:
        return self._response


class FakeAnthropic:
    """client.beta.messages.create / .stream 만 흉내 낸다."""

    def __init__(self, response: SimpleNamespace, chunks: list[str] | None = None) -> None:
        self.response = response
        self.chunks = chunks if chunks is not None else []
        self.create_calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(
            messages=SimpleNamespace(create=self._create, stream=self._stream)
        )

    def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.create_calls.append(kwargs)
        return self.response

    def _stream(self, **kwargs: Any) -> _FakeStream:
        self.stream_calls.append(kwargs)
        return _FakeStream(self.chunks, self.response)


class FakeClaude:
    """Jev가 쓰는 ClaudeClient 대역. ask_stream도 지원한다."""

    def __init__(self, refused: bool = False, chunks: list[str] | None = None) -> None:
        self.calls: list[tuple[list[dict[str, Any]], str]] = []
        self.refused = refused
        self.chunks = chunks or ["응", "답"]

    def ask(self, messages, effort):
        self.calls.append((list(messages), effort))
        content = [{"type": "text", "text": "응답"}]
        return ClaudeReply("응답", content, refused=self.refused)

    def ask_stream(self, messages, effort, on_text):
        for chunk in self.chunks:
            on_text(chunk)
        return self.ask(messages, effort)


class AskOnlyClaude:
    """스트리밍을 지원하지 않는 Claude 대역."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[dict[str, Any]], str]] = []

    def ask(self, messages, effort):
        self.calls.append((list(messages), effort))
        return ClaudeReply("응답", [{"type": "text", "text": "응답"}])
