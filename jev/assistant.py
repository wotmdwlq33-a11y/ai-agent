"""Jev 본체: 라우팅 결과에 따라 로컬 기능 또는 Claude를 호출한다."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from jev import korean, local_skills
from jev.claude_client import ClaudeClient, ClaudeReply, TextCallback
from jev.config import Config
from jev.memory import (
    EMPTY_REPLY,
    ConversationStore,
    HistoryError,
    has_visible_content,
    trim_history,
)
from jev.router import Route, route


class ClaudeLike(Protocol):
    """Jev가 쓰는 Claude 클라이언트의 최소 인터페이스 (테스트에서는 가짜로 바꿔 끼운다)."""

    def ask(self, messages: list[dict[str, Any]], effort: str) -> ClaudeReply: ...


@runtime_checkable
class StreamingClaudeLike(ClaudeLike, Protocol):
    """스트리밍 호출(ask_stream)도 지원하는 Claude 클라이언트."""

    def ask_stream(
        self, messages: list[dict[str, Any]], effort: str, on_text: TextCallback
    ) -> ClaudeReply: ...


@dataclass
class Answer:
    """Jev.handle()의 결과: 보여 줄 답과 라우팅 정보."""

    text: str
    route: Route
    # True면 답변 텍스트가 이미 on_text로 모두 출력되었다.
    streamed: bool = False
    # 스트리밍 중 거절되어 이미 출력한 부분 답변을 무시해야 할 때 True
    refused: bool = False
    # 답은 했지만 사용자에게 알려야 할 문제 (예: 대화 기록 저장 실패)
    warning: str | None = None


class Jev:
    """요청을 라우팅해 로컬 기능 또는 Claude로 처리하고 대화 기록을 관리한다."""

    def __init__(
        self,
        claude: ClaudeLike | None = None,
        *,
        config: Config | None = None,
        store: ConversationStore | None = None,
        clock: Callable[[], datetime] = korean.now,
    ) -> None:
        self._claude = claude
        self._clock = clock
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
        """메모·알림·대화 기록을 저장하는 폴더."""
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
            if decision.skill == "status":
                return Answer(self.status_text(), decision)
            reply_text = local_skills.run(
                decision.skill, text=text, args=decision.args, data_dir=self.data_dir
            )
            return Answer(reply_text, decision)

        assert decision.effort is not None
        claude = self._get_claude()
        messages = [*self.history, {"role": "user", "content": self._user_content(text)}]
        streamed = False
        if on_text is not None and isinstance(claude, StreamingClaudeLike):
            reply = claude.ask_stream(messages, effort=decision.effort, on_text=on_text)
            streamed = True
        else:
            reply = claude.ask(messages, effort=decision.effort)

        warning = None
        if not reply.refused:
            content: Any = reply.content
            if not has_visible_content(content):
                # thinking만 있거나 비어 있는 응답을 그대로 남기면 다음 요청이 거부된다
                content = [{"type": "text", "text": reply.text.strip() or EMPTY_REPLY}]
            warning = self._remember([*messages, {"role": "assistant", "content": content}])
        return Answer(
            reply.text, decision, streamed=streamed, refused=reply.refused, warning=warning
        )

    def status_text(self) -> str:
        """현재 설정 요약. API 키 값은 절대 보여 주지 않고 설정 여부만 알린다."""
        cfg = self.config
        has_key = bool(
            os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        )
        on_off = {True: "켜짐", False: "꺼짐"}
        lines = [
            "현재 설정이에요:",
            f"- 모델(JEV_MODEL): {cfg.model or '설정 안 됨 — Claude를 쓰려면 필요해요'}",
            "- API 키: "
            + (
                "환경변수에 있음"
                if has_key
                else "환경변수에 없음 (`ant auth login`을 썼다면 괜찮아요)"
            ),
            f"- 데이터 폴더(JEV_HOME): {cfg.data_dir}",
            f"- 대화 기록 저장: {on_off[cfg.memory_enabled]} "
            f"(지금 {len(self.history)}개 메시지, 최대 {cfg.max_history_messages}개)",
            f"- 스트리밍 출력: {on_off[cfg.stream]}",
            f"- 현재 시각 전달: {on_off[cfg.send_time]}",
        ]
        return "\n".join(lines)

    def _user_content(self, text: str) -> str:
        """Claude에게 보낼 사용자 메시지. 설정에 따라 현재 시각을 앞에 붙인다.

        시스템 프롬프트에 날짜를 넣으면 매일 바뀌어 캐시와 이전 thinking 블록이 무효가 되므로,
        새 메시지에만 붙여 기록은 뒤에 덧붙이기만 하도록 유지한다.
        """
        if not self.config.send_time:
            return text
        now = korean.localize(self._clock())
        ampm = "오전" if now.hour < 12 else "오후"
        stamp = f"{korean.format_date(now.date())} {ampm} {now.hour % 12 or 12}시 {now.minute}분"
        return f"[현재 시각: {stamp} (한국 시간)]\n{text}"

    def _get_claude(self) -> ClaudeLike:
        if self._claude is None:
            self._claude = ClaudeClient(
                model=self.config.require_model(), max_tokens=self.config.max_tokens
            )
        return self._claude

    def _remember(self, messages: list[dict[str, Any]]) -> str | None:
        """기록을 갱신·저장한다.

        파일 저장에 실패해도 이번 실행 중 기록은 유지하고, 경고 문구를 돌려준다.
        """
        messages, _ = trim_history(
            messages, self.config.max_history_messages, self.config.max_history_bytes
        )
        self.history = messages
        if self._store:
            try:
                self._store.save(messages)
            except HistoryError as e:
                return str(e)
        return None
