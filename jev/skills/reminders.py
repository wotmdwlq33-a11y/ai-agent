"""로컬 리마인더: data_dir/reminders.json 에 저장한다 (Claude 호출 없음).

CLI는 매 입력 전에 pop_due()를 불러 시간이 된 알림을 보여준다.
한 프로세스에서 쓰는 것을 전제로 하며, 파일 잠금은 하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from jev.korean import localize
from jev.storage import StorageError, load_records, save_records

REMINDER_FILE = "reminders.json"
MAX_REMINDER_LENGTH = 1000
MAX_REMINDERS = 1000


class ReminderError(ValueError):
    """사용자 입력 문제. 메시지는 그대로 보여줘도 된다."""


@dataclass(frozen=True)
class Reminder:
    text: str
    due: datetime  # tz-aware, Asia/Seoul
    id: int = field(default=0, compare=False)


def reminder_path(data_dir: Path) -> Path:
    return data_dir / REMINDER_FILE


def _load(data_dir: Path) -> list[Reminder]:
    path = reminder_path(data_dir)
    result: list[Reminder] = []
    for record in load_records(path):
        rid, text, due = record.get("id"), record.get("text"), record.get("due")
        try:
            if not isinstance(rid, int) or not isinstance(text, str) or not isinstance(due, str):
                raise ValueError
            result.append(Reminder(text, localize(datetime.fromisoformat(due)), rid))
        except ValueError as e:
            raise StorageError(
                f"저장 파일({path})에 잘못된 알림이 있어요. "
                "파일을 고치거나 다른 곳으로 옮긴 뒤 다시 시도해 주세요."
            ) from e
    return result


def _save(data_dir: Path, items: list[Reminder]) -> None:
    records: list[dict[str, Any]] = [
        {"id": r.id, "text": r.text, "due": r.due.isoformat()} for r in items
    ]
    save_records(reminder_path(data_dir), records)


def add(data_dir: Path, text: str, due: datetime) -> Reminder:
    """알림을 추가한다. 입력이 잘못되면 ReminderError, 파일 문제면 StorageError."""
    text = text.strip()
    if not text:
        raise ReminderError("알려드릴 내용이 비어 있어요.")
    if len(text) > MAX_REMINDER_LENGTH:
        raise ReminderError(f"알림 내용이 너무 길어요. {MAX_REMINDER_LENGTH}자 이하로 줄여 주세요.")
    items = _load(data_dir)
    if len(items) >= MAX_REMINDERS:
        raise ReminderError(f"알림은 최대 {MAX_REMINDERS}개까지 저장할 수 있어요.")
    reminder = Reminder(text, localize(due), max((r.id for r in items), default=0) + 1)
    _save(data_dir, [*items, reminder])
    return reminder


def list_pending(data_dir: Path, now: datetime) -> list[Reminder]:
    """아직 시간이 안 된 알림을 시간순으로."""
    now = localize(now)
    return sorted((r for r in _load(data_dir) if r.due > now), key=lambda r: r.due)


def pop_due(data_dir: Path, now: datetime) -> list[Reminder]:
    """시간이 된(due <= now) 알림을 시간순으로 돌려주고 저장소에서 지운다.

    파일이 없으면 빈 목록. 파일이 깨졌으면 StorageError (파일은 건드리지 않음).
    """
    now = localize(now)
    items = _load(data_dir)
    due = sorted((r for r in items if r.due <= now), key=lambda r: r.due)
    if due:
        _save(data_dir, [r for r in items if r.due > now])
    return due
