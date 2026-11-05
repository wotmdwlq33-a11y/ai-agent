"""Claude API 호출부."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import anthropic

# 사용할 Claude 모델 ID. 환경변수 JEV_MODEL 로 지정한다.
MODEL_ENV = "JEV_MODEL"
MAX_TOKENS = 16000

SYSTEM_PROMPT = """\
너는 사용자의 개인 비서 Jev야. 한국어로, 친근하지만 간결하게 답해.
모르는 것은 모른다고 말하고, 추측이면 추측이라고 밝혀."""


@dataclass
class ClaudeReply:
    text: str
    # 대화 기록에 그대로 다시 넣어야 하는 content 블록 (thinking 블록 포함)
    content: list[Any]
    refused: bool = False


class ClaudeClient:
    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self._client = client or anthropic.Anthropic()

    def ask(self, messages: list[dict[str, Any]], effort: str) -> ClaudeReply:
        # 안전 분류기가 거절하면 서버가 다른 모델로 다시 시도한다 (fallbacks="default").
        model = os.environ.get(MODEL_ENV)
        if not model:
            raise RuntimeError(f"환경변수 {MODEL_ENV} 에 사용할 Claude 모델 ID를 지정하세요.")
        response = self._client.beta.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=messages,
            output_config={"effort": effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )

        if response.stop_reason == "refusal":
            return ClaudeReply("이 요청은 도와드리기 어려워요.", response.content, refused=True)

        text = "".join(block.text for block in response.content if block.type == "text")
        if response.stop_reason == "max_tokens":
            text += "\n\n(답변이 길어서 중간에 잘렸어요.)"
        return ClaudeReply(text, response.content)
