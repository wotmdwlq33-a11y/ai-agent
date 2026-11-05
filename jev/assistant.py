"""Jev 본체: 라우팅 결과에 따라 로컬 기능 또는 Claude를 호출한다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jev import local_skills
from jev.claude_client import ClaudeClient
from jev.router import Route, route


@dataclass
class Answer:
    text: str
    route: Route


class Jev:
    def __init__(self, claude: ClaudeClient | None = None) -> None:
        self._claude = claude
        # Claude와의 대화 기록. 앞부분을 수정하지 않고 뒤에 덧붙이기만 한다.
        self.history: list[dict[str, Any]] = []

    def handle(self, text: str) -> Answer:
        decision = route(text)

        if decision.target == "local":
            if decision.skill == "reset":
                self.history.clear()
                return Answer("대화 기록을 지웠어요.", decision)
            return Answer(local_skills.run(decision.skill), decision)

        if self._claude is None:
            self._claude = ClaudeClient()
        messages = self.history + [{"role": "user", "content": text}]
        reply = self._claude.ask(messages, effort=decision.effort)
        if not reply.refused:
            self.history = messages + [{"role": "assistant", "content": reply.content}]
        return Answer(reply.text, decision)
