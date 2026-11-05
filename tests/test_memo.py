from datetime import datetime

import pytest

from jev.skills import memo
from jev.storage import StorageError

NOW = datetime(2026, 11, 5, 10, 0, tzinfo=memo.TIMEZONE)


def test_missing_file_is_empty(tmp_path):
    assert memo.list_memos(tmp_path / "nope") == []
    assert memo.search(tmp_path / "nope", "우유") == []


def test_add_and_list(tmp_path):
    data_dir = tmp_path / "new" / "dir"  # 없는 디렉터리는 만든다
    first = memo.add(data_dir, "  우유 사기 ", now=NOW)
    second = memo.add(data_dir, "빵 사기", now=NOW)
    assert (first.id, first.text) == (1, "우유 사기")
    assert first.created_at == "2026-11-05T10:00:00+09:00"
    assert second.id == 2
    assert memo.list_memos(data_dir) == [first, second]
    assert (data_dir / "memos.json").exists()
    # 임시 파일이 남지 않는다
    assert [p.name for p in data_dir.iterdir()] == ["memos.json"]


def test_file_is_utf8_json(tmp_path):
    memo.add(tmp_path, "한글 메모", now=NOW)
    assert "한글 메모" in (tmp_path / "memos.json").read_text(encoding="utf-8")


def test_search_is_case_insensitive_and_all_words(tmp_path):
    memo.add(tmp_path, "우유 사기", now=NOW)
    memo.add(tmp_path, "Buy MILK and eggs", now=NOW)
    memo.add(tmp_path, "우유 마시기 운동", now=NOW)
    assert [m.id for m in memo.search(tmp_path, "우유")] == [1, 3]
    assert [m.id for m in memo.search(tmp_path, "milk")] == [2]
    assert [m.id for m in memo.search(tmp_path, "우유 운동")] == [3]
    assert memo.search(tmp_path, "   ") == []


def test_delete(tmp_path):
    memo.add(tmp_path, "a", now=NOW)
    memo.add(tmp_path, "b", now=NOW)
    removed = memo.delete(tmp_path, 1)
    assert removed is not None and removed.text == "a"
    assert memo.delete(tmp_path, 1) is None
    assert [m.text for m in memo.list_memos(tmp_path)] == ["b"]
    # 지운 번호를 다시 쓰지 않도록 가장 큰 번호 + 1
    assert memo.add(tmp_path, "c", now=NOW).id == 3


def test_empty_memo_rejected(tmp_path):
    with pytest.raises(memo.MemoError, match="비어"):
        memo.add(tmp_path, "   ")


def test_too_long_memo_rejected(tmp_path):
    memo.add(tmp_path, "가" * memo.MAX_MEMO_LENGTH, now=NOW)
    with pytest.raises(memo.MemoError, match="너무 길어요"):
        memo.add(tmp_path, "가" * (memo.MAX_MEMO_LENGTH + 1))


def test_max_count(tmp_path, monkeypatch):
    monkeypatch.setattr(memo, "MAX_MEMOS", 2)
    memo.add(tmp_path, "a", now=NOW)
    memo.add(tmp_path, "b", now=NOW)
    with pytest.raises(memo.MemoError, match="최대 2개"):
        memo.add(tmp_path, "c", now=NOW)


def test_corrupt_file_raises_and_is_preserved(tmp_path):
    path = tmp_path / "memos.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(StorageError, match="손상"):
        memo.list_memos(tmp_path)
    with pytest.raises(StorageError):
        memo.add(tmp_path, "새 메모", now=NOW)
    assert path.read_text(encoding="utf-8") == "{not json"


@pytest.mark.parametrize("content", ['{"id": 1}', "[1, 2]", '[{"id": "x", "text": "a"}]'])
def test_wrong_shape_raises(tmp_path, content):
    (tmp_path / "memos.json").write_text(content, encoding="utf-8")
    with pytest.raises(StorageError):
        memo.list_memos(tmp_path)


def test_empty_file_is_empty(tmp_path):
    (tmp_path / "memos.json").write_text("\n", encoding="utf-8")
    assert memo.list_memos(tmp_path) == []


def test_ids_not_reused_after_deleting_newest(tmp_path):
    memo.add(tmp_path, "a", now=NOW)
    memo.add(tmp_path, "b", now=NOW)
    memo.delete(tmp_path, 2)
    assert memo.add(tmp_path, "c", now=NOW).id == 3
    memo.delete(tmp_path, 3)
    memo.delete(tmp_path, 1)
    assert memo.list_memos(tmp_path) == []
    assert memo.add(tmp_path, "d", now=NOW).id == 4


def test_reads_old_plain_list_files(tmp_path):
    (tmp_path / "memos.json").write_text(
        '[{"id": 5, "text": "옛 메모", "created_at": "2026-01-01T00:00:00+09:00"}]',
        encoding="utf-8",
    )
    assert [m.text for m in memo.list_memos(tmp_path)] == ["옛 메모"]
    assert memo.add(tmp_path, "새 메모", now=NOW).id == 6


def test_naive_now_is_seoul(tmp_path):
    saved = memo.add(tmp_path, "x", now=datetime(2026, 11, 5, 10, 0))
    assert saved.created_at == "2026-11-05T10:00:00+09:00"
