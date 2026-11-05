"""대화 기록을 JSON 파일로 저장하고 불러온다.

크기 제한
- 메시지 개수(`max_messages`)와 JSON 크기(`max_bytes`) 두 가지로 제한한다.
- 한도를 넘으면 오래된 대화부터 사용자/Jev 한 쌍씩 지워, 한도의 절반 정도까지 줄인다.
  매 턴 조금씩 지우면 대화 앞부분이 계속 바뀌므로, 한 번에 넉넉히 줄인다.

thinking 블록 처리
- Claude는 응답의 thinking 블록이 만들어진 뒤 그 앞의 대화가 바뀌면 그 블록을 거부할 수 있다.
- 그래서 앞부분을 지울 때와 파일에서 불러올 때는 thinking 블록을 모두 빼고 텍스트만 남긴다.
  (이전 추론은 잃지만 요청이 실패하지 않는다.)
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from jev.storage import StorageError, write_json_atomic

FORMAT_VERSION = 1
# 내용이 없는 응답을 기록에 남길 때 쓰는 문구 (API는 빈 텍스트를 거부한다)
EMPTY_REPLY = "(빈 응답)"
_THINKING_TYPES = {"thinking", "redacted_thinking"}

Message = dict[str, Any]


class HistoryError(StorageError):
    """대화 기록 파일을 읽거나 쓸 수 없을 때."""


def to_jsonable(content: Any) -> Any:
    """SDK 응답 블록(pydantic 모델)을 JSON으로 저장할 수 있는 dict로 바꾼다."""
    if isinstance(content, str | int | float | bool) or content is None:
        return content
    if isinstance(content, dict):
        return {k: to_jsonable(v) for k, v in content.items()}
    if isinstance(content, list | tuple):
        return [to_jsonable(v) for v in content]
    dump = getattr(content, "model_dump", None)
    if callable(dump):
        return dump(mode="json", exclude_none=True)
    raise TypeError(f"JSON으로 저장할 수 없는 값: {type(content).__name__}")


def _block_type(block: Any) -> str | None:
    value = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
    return value if isinstance(value, str) else None


def _is_empty_text(block: Any) -> bool:
    if _block_type(block) != "text":
        return False
    text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
    return not (isinstance(text, str) and text.strip())


def has_visible_content(content: Any) -> bool:
    """API에 다시 보낼 수 있는 내용(비어 있지 않은 텍스트 등)이 있는지.

    API는 빈 content와 빈 텍스트 블록을 거부한다. thinking 블록만 있는 응답도
    thinking을 빼고 나면 비게 되므로 내용이 없는 것으로 본다.
    """
    if isinstance(content, str):
        return bool(content.strip())
    if not isinstance(content, list):
        return False
    return any(_block_type(b) not in _THINKING_TYPES and not _is_empty_text(b) for b in content)


def strip_thinking(messages: Iterable[Message]) -> list[Message]:
    """assistant 메시지에서 thinking 블록과 빈 텍스트 블록을 뺀다.

    남는 내용이 없으면 API가 받아들이도록 자리표시 텍스트(EMPTY_REPLY)를 넣는다.
    """
    result: list[Message] = []
    for message in messages:
        content = message.get("content")
        if message.get("role") == "assistant" and isinstance(content, list):
            kept = [
                b
                for b in content
                if _block_type(b) not in _THINKING_TYPES and not _is_empty_text(b)
            ]
            if not kept:
                kept = [{"type": "text", "text": EMPTY_REPLY}]
            message = {**message, "content": kept}
        result.append(message)
    return result


def _size(messages: list[Message]) -> int:
    return len(json.dumps(to_jsonable(messages), ensure_ascii=False).encode("utf-8"))


def _drop_oldest_turn(messages: list[Message]) -> list[Message]:
    """맨 앞의 사용자 메시지 하나와 그 뒤 assistant 메시지들을 지운다."""
    i = 1
    while i < len(messages) and messages[i].get("role") != "user":
        i += 1
    return messages[i:]


def _user_turns(messages: list[Message]) -> int:
    return sum(1 for m in messages if m.get("role") == "user")


def trim_history(
    messages: list[Message], max_messages: int, max_bytes: int
) -> tuple[list[Message], bool]:
    """한도를 넘으면 오래된 턴부터 지운다. (결과, 잘렸는지)를 돌려준다.

    잘렸다면 남은 메시지에서도 thinking 블록을 뺀다(모듈 설명 참고).
    """
    if len(messages) <= max_messages and _size(messages) <= max_bytes:
        return messages, False

    target_count = max(2, max_messages // 2)
    target_bytes = max_bytes // 2
    trimmed = strip_thinking(messages)
    # 가장 최근 턴 하나는 한도를 넘더라도 남긴다
    while _user_turns(trimmed) > 1 and (
        len(trimmed) > target_count or _size(trimmed) > target_bytes
    ):
        trimmed = _drop_oldest_turn(trimmed)
    # 첫 메시지는 항상 사용자 메시지여야 한다
    while trimmed and trimmed[0].get("role") != "user":
        trimmed = trimmed[1:]
    return trimmed, True


class ConversationStore:
    """대화 기록 JSON 파일. 쓰기는 임시 파일에 쓴 뒤 교체해서 중간에 끊겨도 깨지지 않게 한다."""

    def __init__(self, path: Path, max_messages: int = 40, max_bytes: int = 200_000) -> None:
        self.path = path
        self.max_messages = max_messages
        self.max_bytes = max_bytes

    def load(self) -> list[Message]:
        """저장된 기록을 불러온다. 파일이 없으면 빈 기록, 깨졌으면 백업 후 빈 기록."""
        try:
            raw = self.path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            self._backup_corrupt()
            return []
        except FileNotFoundError:
            return []
        except OSError as e:
            raise HistoryError(f"대화 기록을 읽을 수 없어요: {self.path} ({e.strerror})") from e

        try:
            data = json.loads(raw)
            messages = data["messages"]
            if data.get("version") != FORMAT_VERSION or not isinstance(messages, list):
                raise ValueError("unsupported format")
            if not all(
                isinstance(m, dict) and m.get("role") in {"user", "assistant"} for m in messages
            ):
                raise ValueError("bad message")
        except (ValueError, KeyError, TypeError):
            self._backup_corrupt()
            return []

        messages = strip_thinking(messages)
        messages, _ = trim_history(messages, self.max_messages, self.max_bytes)
        return messages

    def save(self, messages: list[Message]) -> None:
        """기록을 파일에 저장한다. 실패하면 HistoryError."""
        payload = {"version": FORMAT_VERSION, "messages": to_jsonable(messages)}
        try:
            write_json_atomic(self.path, payload, indent=1)
        except StorageError as e:
            raise HistoryError(f"대화 기록을 저장할 수 없어요: {e}") from e

    def clear(self) -> None:
        """기록 파일을 지운다. 파일이 없어도 오류가 아니다."""
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()

    def _backup_corrupt(self) -> None:
        backup = self.path.with_suffix(".corrupt.json")
        with contextlib.suppress(OSError):
            os.replace(self.path, backup)
