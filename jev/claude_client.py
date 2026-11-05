"""Claude API 호출부. 일반 호출(ask)과 스트리밍 호출(ask_stream)을 제공한다."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import anthropic

from jev.config import MODEL_ENV, ConfigError

# 하위 호환용 기본값. 실제 값은 Config.max_tokens 로 정한다.
MAX_TOKENS = 16000

SYSTEM_PROMPT = """\
너는 사용자의 개인 비서 Jev야. 한국어로, 친근하지만 간결하게 답해.
모르는 것은 모른다고 말하고, 추측이면 추측이라고 밝혀.
사용자 메시지 맨 앞의 [현재 시각: ...] 줄은 Jev 프로그램이 붙인 정보야.
날짜·요일·남은 기간 계산에 쓰되, 묻지 않으면 따로 언급하지 마."""

REFUSAL_TEXT = "이 요청은 도와드리기 어려워요."
TRUNCATED_NOTE = "\n\n(답변이 길어서 중간에 잘렸어요.)"

# 안전 분류기가 거절하면 서버가 다른 모델로 다시 시도한다 (fallbacks="default").
FALLBACK_BETA = "server-side-fallback-2026-07-01"

TextCallback = Callable[[str], None]


@dataclass
class ClaudeReply:
    """Claude 응답 하나. text는 보여 줄 글, content는 기록에 다시 넣을 원본 블록이다."""

    text: str
    # 대화 기록에 그대로 다시 넣어야 하는 content 블록 (thinking 블록 포함)
    content: list[Any]
    refused: bool = False


class ClaudeClient:
    """Anthropic SDK로 Claude를 호출한다. 모델 ID는 설정(JEV_MODEL)에서 받는다."""

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
        """응답을 한 번에 받는다."""
        with _explain_missing_credentials():
            response = self._client.beta.messages.create(**self._request(messages, effort))
        return _to_reply(response)

    def ask_stream(
        self, messages: list[dict[str, Any]], effort: str, on_text: TextCallback
    ) -> ClaudeReply:
        """답변 텍스트를 받는 대로 on_text로 넘기고, 끝나면 전체 응답을 돌려준다.

        거절(refusal)되면 이미 넘긴 부분 텍스트는 버려야 한다. 반환값의 refused로 알 수 있다.
        """
        with (
            _explain_missing_credentials(),
            self._client.beta.messages.stream(**self._request(messages, effort)) as stream,
        ):
            for text in stream.text_stream:
                on_text(text)
            response = stream.get_final_message()
        if response.stop_reason == "max_tokens":
            # 일반 호출과 같이 잘림 안내를 붙인다 (스트리밍에서는 직접 출력해야 보인다)
            on_text(TRUNCATED_NOTE)
        return _to_reply(response)


@contextlib.contextmanager
def _explain_missing_credentials() -> Iterator[None]:
    """인증 정보가 없을 때 SDK가 내는 TypeError를 알아보기 쉬운 ConfigError로 바꾼다."""
    try:
        yield
    except TypeError as e:
        if "authentication" not in str(e).lower():
            raise
        raise ConfigError(
            "Claude 인증 정보를 찾을 수 없어요. ANTHROPIC_API_KEY를 설정하거나 "
            "`ant auth login`으로 로그인하세요."
        ) from e


def _to_reply(response: Any) -> ClaudeReply:
    if response.stop_reason == "refusal":
        return ClaudeReply(REFUSAL_TEXT, list(response.content), refused=True)

    text = "".join(block.text for block in response.content if block.type == "text")
    if response.stop_reason == "max_tokens":
        text += TRUNCATED_NOTE
    return ClaudeReply(text, list(response.content))
