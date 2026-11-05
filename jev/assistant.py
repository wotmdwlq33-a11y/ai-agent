"""Jev 본체: 라우팅 결과에 따라 로컬 기능 또는 Claude를 호출한다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from jev import local_skills
from jev.claude_client import ClaudeClient, ClaudeReply, TextCallback
from jev.config import Config
from jev.memory import ConversationStore, trim_history
from jev.router import Route, route


class ClaudeLike(Protocol):
    def ask(self, messages: list[dict[str, Any]], effort: str) -> ClaudeReply: ...


@runtime_checkable
class StreamingClaudeLike(ClaudeLike, Protocol):
    def ask_stream(
        self, messages: list[dict[str, Any]], effort: str, on_text: TextCallback
    ) -> ClaudeReply: ...


@dataclass
class Answer:
    text: str
    route: Route
    # True면 답변 텍스트가 이미 on_text로 모두 출력되었다.
    streamed: bool = False
    # 스트리밍 중 거절되어 이미 출력한 부분 답변을 무시해야 할 때 True
    refused: bool = False


class Jev:
    def __init__(
        self,
        claude: ClaudeLike | None = None,
        *,
        config: Config | None = None,
        store: ConversationStore | None = None,
    ) -> None:
        self._claude = claude
        self.config = config or Config.from_env()
        if store is None and self.config.memory_enabled:
            store = ConversationStore(
                self.config.history_path,
                max_messages=self.config.max_history_messages,
                max_bytes=self.config.max_history_bytes,
            )
        self._store = store
        # Claude와의 대화 기록. 한도를 넘기 전까지는 뒤에 덧붙이기만 한다.
        self.history: list[dict[str, Any]] = store.load() if store else []

    @property
    def data_dir(self) -> Path:
        return self.config.data_dir

    def handle(self, text: str, on_text: TextCallback | None = None) -> Answer:
        """요청 하나를 처리한다. on_text를 주면 Claude 답변을 스트리밍으로 넘긴다."""
        decision = route(text)

        if decision.target == "local":
            assert decision.skill is not None
            if decision.skill == "reset":
                self.history.clear()
                if self._store:
                    self._store.clear()
                return Answer("대화 기록을 지웠어요.", decision)
            reply_text = local_skills.run(
                decision.skill, text=text, args=decision.args, data_dir=self.data_dir
            )
            return Answer(reply_text, decision)

        assert decision.effort is not None
        claude = self._get_claude()
        messages = [*self.history, {"role": "user", "content": text}]
        streamed = False
        if on_text is not None and isinstance(claude, StreamingClaudeLike):
            reply = claude.ask_stream(messages, effort=decision.effort, on_text=on_text)
            streamed = True
        else:
            reply = claude.ask(messages, effort=decision.effort)

        if not reply.refused:
            self._remember([*messages, {"role": "assistant", "content": reply.content}])
        return Answer(reply.text, decision, streamed=streamed, refused=reply.refused)

    def _get_claude(self) -> ClaudeLike:
        if self._claude is None:
            self._claude = ClaudeClient(
                model=self.config.require_model(), max_tokens=self.config.max_tokens
            )
        return self._claude

    def _remember(self, messages: list[dict[str, Any]]) -> None:
        messages, _ = trim_history(
            messages, self.config.max_history_messages, self.config.max_history_bytes
        )
        if self._store:
            self._store.save(messages)
        self.history = messages
