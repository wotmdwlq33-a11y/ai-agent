import json
from datetime import UTC, datetime, timedelta

import pytest

from jev.skills import StorageError, reminders
from jev.skills.reminders import Reminder

NOW = datetime(2026, 11, 5, 10, 0, tzinfo=reminders.TIMEZONE)


def test_missing_file(tmp_path):
    assert reminders.list_pending(tmp_path, NOW) == []
    assert reminders.pop_due(tmp_path, NOW) == []
    assert not (tmp_path / "reminders.json").exists()


def test_add_list_and_pop(tmp_path):
    later = reminders.add(tmp_path, "회의", NOW + timedelta(hours=1))
    sooner = reminders.add(tmp_path, "물 마시기", NOW + timedelta(minutes=10))
    assert later.id == 1 and sooner.id == 2

    pending = reminders.list_pending(tmp_path, NOW)
    assert [r.text for r in pending] == ["물 마시기", "회의"]

    assert reminders.pop_due(tmp_path, NOW + timedelta(minutes=5)) == []

    due = reminders.pop_due(tmp_path, NOW + timedelta(minutes=10))
    assert due == [Reminder("물 마시기", NOW + timedelta(minutes=10))]
    assert isinstance(due[0].text, str)
    assert due[0].due.tzinfo is not None
    # 한 번 꺼낸 알림은 다시 나오지 않는다
    assert reminders.pop_due(tmp_path, NOW + timedelta(minutes=10)) == []
    assert [r.text for r in reminders.list_pending(tmp_path, NOW)] == ["회의"]


def test_pop_due_returns_in_due_order(tmp_path):
    reminders.add(tmp_path, "b", NOW + timedelta(minutes=2))
    reminders.add(tmp_path, "a", NOW + timedelta(minutes=1))
    due = reminders.pop_due(tmp_path, NOW + timedelta(hours=1))
    assert [r.text for r in due] == ["a", "b"]
    assert reminders.list_pending(tmp_path, NOW) == []


def test_due_roundtrips_timezone(tmp_path):
    utc_due = datetime(2026, 11, 4, 18, 0, tzinfo=UTC)  # = 서울 11월 5일 03:00
    reminders.add(tmp_path, "x", utc_due)
    stored = json.loads((tmp_path / "reminders.json").read_text(encoding="utf-8"))
    assert stored[0]["due"] == "2026-11-05T03:00:00+09:00"
    assert reminders.list_pending(tmp_path, NOW - timedelta(days=1))[0].due == utc_due


def test_validation(tmp_path, monkeypatch):
    with pytest.raises(reminders.ReminderError):
        reminders.add(tmp_path, "  ", NOW)
    with pytest.raises(reminders.ReminderError, match="너무 길어요"):
        reminders.add(tmp_path, "가" * (reminders.MAX_REMINDER_LENGTH + 1), NOW)
    monkeypatch.setattr(reminders, "MAX_REMINDERS", 1)
    reminders.add(tmp_path, "a", NOW)
    with pytest.raises(reminders.ReminderError, match="최대 1개"):
        reminders.add(tmp_path, "b", NOW)


def test_corrupt_file(tmp_path):
    path = tmp_path / "reminders.json"
    path.write_text("[{", encoding="utf-8")
    with pytest.raises(StorageError):
        reminders.pop_due(tmp_path, NOW)
    assert path.read_text(encoding="utf-8") == "[{"


def test_bad_due_value(tmp_path):
    (tmp_path / "reminders.json").write_text(
        '[{"id": 1, "text": "a", "due": "not a date"}]', encoding="utf-8"
    )
    with pytest.raises(StorageError):
        reminders.list_pending(tmp_path, NOW)
