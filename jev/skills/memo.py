"""로컬 메모: data_dir/memos.json 에 저장한다 (Claude 호출 없음)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from jev.korean import TIMEZONE, localize
from jev.storage import StorageError, file_lock, load_records, save_records

MEMO_FILE = "memos.json"
MAX_MEMO_LENGTH = 1000
MAX_MEMOS = 1000
# 파일은 메모 객체의 JSON 배열이다. 다음 번호를 기억하는 메타 레코드 {"_meta": {...}}가
# 맨 앞에 있을 수 있다 (지운 번호를 다시 쓰지 않기 위해). 메타가 없는 예전 파일도 읽는다.
_META = "_meta"


class MemoError(ValueError):
    """사용자 입력 문제(빈 메모, 너무 긴 메모, 개수 초과). 메시지는 그대로 보여줘도 된다."""


@dataclass(frozen=True)
class Memo:
    """메모 하나. created_at은 한국 시간 ISO 문자열."""

    id: int
    text: str
    created_at: str  # ISO 8601, Asia/Seoul


def memo_path(data_dir: Path) -> Path:
    """메모 저장 파일 경로."""
    return data_dir / MEMO_FILE


def _load(data_dir: Path) -> list[Memo]:
    return _load_state(data_dir)[0]


def _load_state(data_dir: Path) -> tuple[list[Memo], int]:
    """(메모 목록, 다음에 쓸 번호)."""
    path = memo_path(data_dir)
    memos: list[Memo] = []
    next_id = 1
    for record in load_records(path):
        if _META in record:
            meta = record[_META]
            stored = meta.get("next_id") if isinstance(meta, dict) else None
            if isinstance(stored, int) and not isinstance(stored, bool):
                next_id = max(next_id, stored)
            continue
        memo_id, text, created = record.get("id"), record.get("text"), record.get("created_at")
        if (
            not isinstance(memo_id, int)
            or isinstance(memo_id, bool)
            or not isinstance(text, str)
            or not isinstance(created, str)
        ):
            raise StorageError(
                f"저장 파일({path})에 잘못된 메모가 있어요. "
                "파일을 고치거나 다른 곳으로 옮긴 뒤 다시 시도해 주세요."
            )
        memos.append(Memo(memo_id, text, created))
    next_id = max(next_id, max((m.id for m in memos), default=0) + 1)
    return memos, next_id


def _save(data_dir: Path, memos: list[Memo], next_id: int) -> None:
    records = [{_META: {"next_id": next_id}}, *(asdict(m) for m in memos)]
    save_records(memo_path(data_dir), records)


def add(data_dir: Path, text: str, now: datetime | None = None) -> Memo:
    """메모를 추가하고 저장된 메모를 돌려준다. 입력이 잘못되면 MemoError."""
    text = text.strip()
    if not text:
        raise MemoError("메모할 내용이 비어 있어요. '메모: 우유 사기'처럼 말해 주세요.")
    if len(text) > MAX_MEMO_LENGTH:
        raise MemoError(
            f"메모가 너무 길어요. {MAX_MEMO_LENGTH}자 이하로 줄여 주세요. (지금 {len(text)}자)"
        )
    created = localize(now or datetime.now(TIMEZONE))
    with file_lock(memo_path(data_dir)):
        memos, next_id = _load_state(data_dir)
        if len(memos) >= MAX_MEMOS:
            raise MemoError(
                f"메모는 최대 {MAX_MEMOS}개까지 저장할 수 있어요. 안 쓰는 메모를 먼저 지워 주세요."
            )
        memo = Memo(
            id=next_id,
            text=text,
            created_at=created.replace(microsecond=0).isoformat(),
        )
        _save(data_dir, [*memos, memo], next_id + 1)
    return memo


def list_memos(data_dir: Path) -> list[Memo]:
    """저장된 순서(오래된 것부터)대로 모든 메모."""
    return _load(data_dir)


def search(data_dir: Path, query: str) -> list[Memo]:
    """대소문자를 무시하고, 공백으로 나뉜 검색어가 모두 들어 있는 메모를 찾는다."""
    words = query.casefold().split()
    if not words:
        return []
    return [m for m in _load(data_dir) if all(w in m.text.casefold() for w in words)]


def delete(data_dir: Path, memo_id: int) -> Memo | None:
    """메모를 지우고 지운 메모를 돌려준다. 없는 번호면 None."""
    with file_lock(memo_path(data_dir)):
        memos, next_id = _load_state(data_dir)
        for memo in memos:
            if memo.id == memo_id:
                _save(data_dir, [m for m in memos if m.id != memo_id], next_id)
                return memo
    return None
