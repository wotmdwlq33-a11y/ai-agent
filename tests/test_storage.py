import json
import multiprocessing
import sys

import pytest

from jev.storage import StorageError, file_lock, load_records, save_records, write_json_atomic


def test_missing_and_empty_files_are_empty(tmp_path):
    assert load_records(tmp_path / "none.json") == []
    (tmp_path / "empty.json").write_text("  \n", encoding="utf-8")
    assert load_records(tmp_path / "empty.json") == []


def test_roundtrip_creates_parent_dir(tmp_path):
    path = tmp_path / "a" / "b" / "items.json"
    save_records(path, [{"id": 1, "text": "한글"}])
    assert load_records(path) == [{"id": 1, "text": "한글"}]
    assert "한글" in path.read_text(encoding="utf-8")  # ensure_ascii=False
    assert sorted(p.name for p in path.parent.iterdir()) == ["items.json"]


@pytest.mark.parametrize("content", ["{broken", '{"not": "a list"}', "[1, 2]"])
def test_corrupt_file_raises_and_is_left_untouched(tmp_path, content):
    path = tmp_path / "items.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(StorageError):
        load_records(path)
    assert path.read_text(encoding="utf-8") == content


def test_write_failure_is_storage_error(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(StorageError):
        write_json_atomic(blocker / "sub" / "x.json", {"a": 1})


def test_write_json_atomic_any_value(tmp_path):
    path = tmp_path / "x.json"
    write_json_atomic(path, {"v": 1}, indent=1)
    assert json.loads(path.read_text(encoding="utf-8")) == {"v": 1}


def _add_memos(data_dir: str, worker: int, count: int) -> None:
    from pathlib import Path

    from jev.skills import memo

    for i in range(count):
        memo.add(Path(data_dir), f"작업자{worker}-{i}")


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl 잠금은 POSIX 전용")
def test_concurrent_processes_do_not_lose_memos(tmp_path):
    from jev.skills import memo

    ctx = multiprocessing.get_context("spawn")
    workers = [ctx.Process(target=_add_memos, args=(str(tmp_path), w, 15)) for w in range(4)]
    for p in workers:
        p.start()
    for p in workers:
        p.join(60)
        assert p.exitcode == 0
    memos = memo.list_memos(tmp_path)
    assert len(memos) == 60
    assert len({m.id for m in memos}) == 60


def test_file_lock_creates_parent_and_releases(tmp_path):
    path = tmp_path / "new" / "data.json"
    with file_lock(path):
        pass
    with file_lock(path):  # 다시 잡을 수 있다
        pass
    assert (tmp_path / "new" / "data.json.lock").exists()
