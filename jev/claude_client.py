"""Claude API 호출부. 일반 호출(ask)과 스트리밍 호출(ask_stream)을 제공한다."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import anthropic

from jev.config import MODEL_ENV, ConfigError

# 하위 호환용 기본값. 실제 값은 Config.max_tokens 로 정한다.
MAX_TOKENS = 16000

SYSTEM_PROMPT = """\
너는 사용자의 개인 비서 Jev야. 한국어로, 친근하지만 간결하게 답해.
모르는 것은 모른다고 말하고, 추측이면 추측이라고 밝혀."""

REFUSAL_TEXT = "이 요청은 도와드리기 어려워요."
TRUNCATED_NOTE = "\n\n(답변이 길어서 중간에 잘렸어요.)"

# 안전 분류기가 거절하면 서버가 다른 모델로 다시 시도한다 (fallbacks="default").
FALLBACK_BETA = "server-side-fallback-2026-07-01"

TextCallback = Callable[[str], None]


@dataclass
class ClaudeReply:
    text: str
    # 대화 기록에 그대로 다시 넣어야 하는 content 블록 (thinking 블록 포함)
    content: list[Any]
    refused: bool = False


class ClaudeClient:
    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        *,
        model: str | None = None,
        max_tokens: int = MAX_TOKENS,
    ) -> None:
        self._client = client or anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    def _model_id(self) -> str:
        model = self._model or os.environ.get(MODEL_ENV)
        if not model:
            raise ConfigError(f"환경변수 {MODEL_ENV} 에 사용할 Claude 모델 ID를 지정하세요.")
        return model

    def _request(self, messages: list[dict[str, Any]], effort: str) -> dict[str, Any]:
        return {
            "model": self._model_id(),
            "max_tokens": self._max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": messages,
            "output_config": {"effort": effort},
            "betas": [FALLBACK_BETA],
            "fallbacks": "default",
        }

    def ask(self, messages: list[dict[str, Any]], effort: str) -> ClaudeReply:
        response = self._client.beta.messages.create(**self._request(messages, effort))
        return _to_reply(response)

    def ask_stream(
        self, messages: list[dict[str, Any]], effort: str, on_text: TextCallback
    ) -> ClaudeReply:
        """답변 텍스트를 받는 대로 on_text로 넘기고, 끝나면 전체 응답을 돌려준다.

        거절(refusal)되면 이미 넘긴 부분 텍스트는 버려야 한다. 반환값의 refused로 알 수 있다.
        """
        with self._client.beta.messages.stream(**self._request(messages, effort)) as stream:
            for text in stream.text_stream:
                on_text(text)
            response = stream.get_final_message()
        return _to_reply(response)


def _to_reply(response: Any) -> ClaudeReply:
    if response.stop_reason == "refusal":
        return ClaudeReply(REFUSAL_TEXT, list(response.content), refused=True)

    text = "".join(block.text for block in response.content if block.type == "text")
    if response.stop_reason == "max_tokens":
        text += TRUNCATED_NOTE
    return ClaudeReply(text, list(response.content))
