"""한국어·한국 시간 관련 공통 도우미."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

__all__ = [
    "TIMEZONE",
    "WEEKDAYS",
    "format_date",
    "has_final_consonant",
    "josa",
    "localize",
    "now",
]

TIMEZONE = ZoneInfo("Asia/Seoul")
WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")


def now() -> datetime:
    """한국 시간 기준 현재 시각."""
    return datetime.now(TIMEZONE)


def localize(dt: datetime) -> datetime:
    """시간대가 없으면 한국 시간으로 보고, 있으면 한국 시간으로 바꾼다."""
    return dt.replace(tzinfo=TIMEZONE) if dt.tzinfo is None else dt.astimezone(TIMEZONE)


def format_date(d: date) -> str:
    """예: "2026년 12월 25일(금)"."""
    return f"{d.year}년 {d.month}월 {d.day}일({WEEKDAYS[d.weekday()]})"


def has_final_consonant(word: str) -> bool:
    """마지막 한글 글자에 받침이 있는지. 괄호·숫자 등 한글이 아닌 끝 글자는 건너뛴다."""
    for ch in reversed(word):
        if "가" <= ch <= "힣":
            return (ord(ch) - ord("가")) % 28 != 0
    return False


def josa(word: str, with_final: str, without_final: str) -> str:
    """word 뒤에 받침에 맞는 조사를 붙인다. 예: josa("성탄절", "이에요", "예요")."""
    return word + (with_final if has_final_consonant(word) else without_final)
