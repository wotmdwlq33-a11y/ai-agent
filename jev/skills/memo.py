"""로컬 메모: data_dir/memos.json 에 저장한다 (Claude 호출 없음)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from jev.korean import TIMEZONE
from jev.storage import StorageError, load_records, save_records

MEMO_FILE = "memos.json"
MAX_MEMO_LENGTH = 1000
MAX_MEMOS = 1000


class MemoError(ValueError):
    """사용자 입력 문제(빈 메모, 너무 긴 메모, 개수 초과). 메시지는 그대로 보여줘도 된다."""


@dataclass(frozen=True)
class Memo:
    id: int
    text: str
    created_at: str  # ISO 8601, Asia/Seoul


def memo_path(data_dir: Path) -> Path:
    return data_dir / MEMO_FILE


def _load(data_dir: Path) -> list[Memo]:
    path = memo_path(data_dir)
    memos: list[Memo] = []
    for record in load_records(path):
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
    return memos


def _save(data_dir: Path, memos: list[Memo]) -> None:
    save_records(memo_path(data_dir), [asdict(m) for m in memos])


def add(data_dir: Path, text: str, now: datetime | None = None) -> Memo:
    """메모를 추가하고 저장된 메모를 돌려준다. 입력이 잘못되면 MemoError."""
    text = text.strip()
    if not text:
        raise MemoError("메모할 내용이 비어 있어요. '메모: 우유 사기'처럼 말해 주세요.")
    if len(text) > MAX_MEMO_LENGTH:
        raise MemoError(
            f"메모가 너무 길어요. {MAX_MEMO_LENGTH}자 이하로 줄여 주세요. (지금 {len(text)}자)"
        )
    memos = _load(data_dir)
    if len(memos) >= MAX_MEMOS:
        raise MemoError(
            f"메모는 최대 {MAX_MEMOS}개까지 저장할 수 있어요. 안 쓰는 메모를 먼저 지워 주세요."
        )
    created = (now or datetime.now(TIMEZONE)).astimezone(TIMEZONE)
    memo = Memo(
        id=max((m.id for m in memos), default=0) + 1,
        text=text,
        created_at=created.replace(microsecond=0).isoformat(),
    )
    _save(data_dir, [*memos, memo])
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
    memos = _load(data_dir)
    for memo in memos:
        if memo.id == memo_id:
            _save(data_dir, [m for m in memos if m.id != memo_id])
            return memo
    return None
