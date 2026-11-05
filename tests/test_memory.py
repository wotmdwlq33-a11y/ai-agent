import json
from types import SimpleNamespace

import pytest

from jev.memory import (
    EMPTY_REPLY,
    ConversationStore,
    has_visible_content,
    strip_thinking,
    to_jsonable,
    trim_history,
)


def turn(i, thinking=False):
    content = [{"type": "text", "text": f"답{i}"}]
    if thinking:
        content.insert(0, {"type": "thinking", "thinking": "", "signature": "sig"})
    return [{"role": "user", "content": f"질문{i}"}, {"role": "assistant", "content": content}]


def history(n, thinking=False):
    return [m for i in range(n) for m in turn(i, thinking)]


class FakeBlock:
    def __init__(self, **data):
        self.data = data

    def model_dump(self, mode, exclude_none):
        assert (mode, exclude_none) == ("json", True)
        return dict(self.data)


def test_to_jsonable_handles_sdk_blocks():
    msgs = [{"role": "assistant", "content": [FakeBlock(type="text", text="hi")]}]
    assert to_jsonable(msgs) == [{"role": "assistant", "content": [{"type": "text", "text": "hi"}]}]


def test_strip_thinking_keeps_text_and_user_messages():
    msgs = history(1, thinking=True)
    msgs.append({"role": "assistant", "content": [SimpleNamespace(type="redacted_thinking")]})
    stripped = strip_thinking(msgs)
    assert stripped[0] == msgs[0]
    assert stripped[1]["content"] == [{"type": "text", "text": "답0"}]
    # API는 빈 텍스트를 거부하므로 자리표시 문구를 넣는다
    assert stripped[2]["content"] == [{"type": "text", "text": EMPTY_REPLY}]
    # 원본은 그대로
    assert msgs[1]["content"][0]["type"] == "thinking"


def test_trim_not_needed_keeps_history_identical():
    msgs = history(3, thinking=True)
    result, trimmed = trim_history(msgs, max_messages=10, max_bytes=100_000)
    assert result is msgs
    assert trimmed is False


def test_trim_by_count_halves_and_strips_thinking():
    msgs = history(6, thinking=True)  # 12 messages
    result, trimmed = trim_history(msgs, max_messages=10, max_bytes=100_000)
    assert trimmed is True
    assert len(result) <= 5 + 1
    assert result[0]["role"] == "user"
    assert result[-1]["content"] == [{"type": "text", "text": "답5"}]
    assert all(b["type"] != "thinking" for m in result[1::2] for b in m["content"])


def test_trim_by_bytes():
    msgs = [m for i in range(5) for m in turn(i)]
    msgs[0]["content"] = "가" * 5000
    result, trimmed = trim_history(msgs, max_messages=100, max_bytes=4000)
    assert trimmed
    assert result[0]["content"] != "가" * 5000
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= 2000


def test_trim_keeps_latest_turn_even_if_too_big():
    msgs = [
        *turn(0),
        {"role": "user", "content": "큰" * 10000},
        {"role": "assistant", "content": "x"},
    ]
    result, _ = trim_history(msgs, max_messages=100, max_bytes=1000)
    assert [m["role"] for m in result] == ["user", "assistant"]
    assert result[0]["content"] == "큰" * 10_000


def test_store_roundtrip(tmp_path):
    store = ConversationStore(tmp_path / "sub" / "history.json")
    assert store.load() == []
    msgs = history(2)
    store.save(msgs)
    assert store.load() == msgs
    data = json.loads(store.path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    # 임시 파일이 남지 않는다
    assert [p.name for p in store.path.parent.iterdir()] == ["history.json"]


def test_store_load_strips_thinking_and_applies_limits(tmp_path):
    store = ConversationStore(tmp_path / "h.json", max_messages=4, max_bytes=100_000)
    store.save(history(5, thinking=True))
    loaded = store.load()
    assert len(loaded) <= 4
    assert loaded[0]["role"] == "user"
    assert all(b["type"] == "text" for m in loaded[1::2] for b in m["content"])


def test_corrupt_file_is_backed_up(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("{not json", encoding="utf-8")
    store = ConversationStore(path)
    assert store.load() == []
    assert not path.exists()
    assert (tmp_path / "history.corrupt.json").read_text(encoding="utf-8") == "{not json"


def test_wrong_shape_is_treated_as_corrupt(tmp_path):
    path = tmp_path / "history.json"
    path.write_text(json.dumps({"version": 1, "messages": [{"role": "system"}]}), encoding="utf-8")
    assert ConversationStore(path).load() == []


def test_clear(tmp_path):
    store = ConversationStore(tmp_path / "h.json")
    store.save(history(1))
    store.clear()
    store.clear()  # 두 번 지워도 오류 없음
    assert store.load() == []


@pytest.mark.parametrize(
    "content, expected",
    [
        ("안녕", True),
        ("  ", False),
        ([], False),
        ([{"type": "text", "text": ""}], False),
        ([{"type": "thinking", "thinking": "", "signature": "s"}], False),
        ([{"type": "thinking", "thinking": ""}, {"type": "text", "text": "답"}], True),
        ([SimpleNamespace(type="text", text="답")], True),
    ],
)
def test_has_visible_content(content, expected):
    assert has_visible_content(content) is expected


def test_non_utf8_history_is_backed_up(tmp_path):
    path = tmp_path / "history.json"
    path.write_bytes(b"\xff\xfe\x00broken")
    assert ConversationStore(path).load() == []
    assert (tmp_path / "history.corrupt.json").exists()
