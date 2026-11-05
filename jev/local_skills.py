"""API 호출 없이 Jev가 직접 처리하는 기능."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Asia/Seoul")
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

HELP_TEXT = """\
저는 Jev입니다. 이렇게 쓸 수 있어요:
- "몇 시야?" / "오늘 날짜" : 바로 답해요 (Claude 호출 없음)
- "/reset" 또는 "초기화" : Claude와의 대화 기록을 지워요
- 그 밖의 질문 : Claude에게 넘겨서 답해요. 어려운 질문일수록 더 깊게 생각하게 합니다."""


def now() -> datetime:
    return datetime.now(TIMEZONE)


def run(skill: str, current: datetime | None = None) -> str:
    current = current or now()
    if skill == "time":
        return f"지금은 {current:%H시 %M분}이에요."
    if skill == "date":
        return f"오늘은 {current:%Y년 %m월 %d일} {WEEKDAYS[current.weekday()]}요일이에요."
    if skill == "help":
        return HELP_TEXT
    raise ValueError(f"알 수 없는 로컬 기능: {skill}")
