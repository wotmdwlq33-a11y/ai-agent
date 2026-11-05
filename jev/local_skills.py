"""API 호출 없이 Jev가 직접 처리하는 기능."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jev.router import route
from jev.skills import StorageError, josa, memo, reminders, timeparse, units

TIMEZONE = ZoneInfo("Asia/Seoul")
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
MEMO_LIST_LIMIT = 30
SEARCH_LIMIT = 30

HELP_TEXT = """\
저는 Jev입니다. 이렇게 쓸 수 있어요 (아래는 모두 Claude 호출 없이 바로 답해요):
- "몇 시야?" / "오늘 날짜" : 지금 시각과 날짜
- "메모: 우유 사기" / "메모 목록" / "메모 검색 우유" / "메모 삭제 3" : 메모
- "10분 뒤에 회의 알려줘" / "내일 9시에 병원 가기 알려줘" / "알림 목록" : 리마인더
- "10km는 몇 마일" / "100 화씨를 섭씨로" / "30평은 몇 제곱미터" : 단위 변환
- "다음 공휴일" / "올해 공휴일" / "오늘 공휴일이야?" : 공휴일
- "12월 25일까지 며칠" / "D-day 2026-12-25" : 남은 날짜 계산
- "/reset" 또는 "초기화" : Claude와의 대화 기록을 지워요
- 그 밖의 질문 : Claude에게 넘겨서 답해요. 어려운 질문일수록 더 깊게 생각하게 합니다."""


def now() -> datetime:
    return datetime.now(TIMEZONE)


def default_data_dir() -> Path:
    return Path.home() / ".jev"


def run(
    skill: str,
    current: datetime | None = None,
    *,
    text: str = "",
    data_dir: Path | None = None,
) -> str:
    """로컬 기능을 실행해 답을 돌려준다.

    text에는 사용자의 원문을 넘긴다. 라우터의 Route.args를 넘겨도 동작한다.
    data_dir이 None이면 ~/.jev 를 쓴다.
    """
    current = current or now()
    if skill == "time":
        return f"지금은 {current:%H시 %M분}이에요."
    if skill == "date":
        return f"오늘은 {current:%Y년 %m월 %d일} {WEEKDAYS[current.weekday()]}요일이에요."
    if skill == "help":
        return HELP_TEXT

    handler = _HANDLERS.get(skill)
    if handler is None:
        raise ValueError(f"알 수 없는 로컬 기능: {skill}")
    decision = route(text)
    args = decision.args if decision.skill == skill else text.strip()
    try:
        return handler(args, current, data_dir or default_data_dir())
    except StorageError as e:
        return str(e)


# ---- 메모 ----


def _short_date(iso: str) -> str:
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{d.month}월 {d.day}일"


def _format_memos(memos: list[memo.Memo]) -> str:
    return "\n".join(f"#{m.id} {m.text} ({_short_date(m.created_at)})" for m in memos)


def _memo_add(args: str, current: datetime, data_dir: Path) -> str:
    if not args:
        return "무엇을 메모할까요? '메모: 우유 사기'처럼 말해 주세요."
    try:
        saved = memo.add(data_dir, args, now=current)
    except memo.MemoError as e:
        return str(e)
    return f"메모했어요 (#{saved.id}): {saved.text}"


def _memo_list(args: str, current: datetime, data_dir: Path) -> str:
    memos = memo.list_memos(data_dir)
    if not memos:
        return "저장된 메모가 없어요. '메모: 우유 사기'처럼 남겨 보세요."
    shown = memos[-MEMO_LIST_LIMIT:]
    head = f"메모가 {len(memos)}개 있어요"
    if len(memos) > len(shown):
        head += f" (최근 {len(shown)}개만 보여드려요)"
    return f"{head}:\n{_format_memos(shown)}"


def _memo_search(args: str, current: datetime, data_dir: Path) -> str:
    if not args:
        return "무엇을 찾을까요? '메모 검색 우유'처럼 말해 주세요."
    found = memo.search(data_dir, args)
    if not found:
        return f"'{args}'(이)가 들어간 메모는 없어요."
    shown = found[-SEARCH_LIMIT:]
    head = f"'{args}' 메모를 {len(found)}개 찾았어요"
    if len(found) > len(shown):
        head += f" (최근 {len(shown)}개만 보여드려요)"
    return f"{head}:\n{_format_memos(shown)}"


def _memo_delete(args: str, current: datetime, data_dir: Path) -> str:
    m = re.search(r"\d+", args)
    if not m:
        return "지울 메모 번호를 알려 주세요. '메모 삭제 3'처럼요."
    removed = memo.delete(data_dir, int(m.group()))
    if removed is None:
        return f"#{m.group()} 메모는 없어요. '메모 목록'으로 번호를 확인해 주세요."
    return f"#{removed.id} 메모를 지웠어요: {removed.text}"


# ---- 리마인더 ----


def _task_text(args: str, start: int, end: int) -> str:
    """시간 표현과 바로 뒤의 조사('에', '에는')를 빼고 남은 할 일."""
    after = re.sub(r"^\s*(?:에는|에|엔)(?=\s|$)", "", args[end:])
    return re.sub(r"\s+", " ", f"{args[:start]} {after}").strip()


def _remind_add(args: str, current: datetime, data_dir: Path) -> str:
    found = timeparse.find_korean_time(args, current)
    if found is None:
        return (
            "언제 알려드릴지 이해하지 못했어요. "
            "'10분 뒤에 회의 알려줘'나 '내일 9시에 병원 가기 알려줘'처럼 말해 주세요."
        )
    due = found.when.replace(microsecond=0)
    if due <= current:
        return "그 시간은 이미 지났어요. 앞으로의 시간을 말해 주세요."
    task = _task_text(args, found.start, found.end) or "알림"
    try:
        reminders.add(data_dir, task, due)
    except reminders.ReminderError as e:
        return str(e)
    return f"알겠어요! {timeparse.format_korean_datetime(due, current)}에 '{task}' 알려드릴게요."


def _remind_list(args: str, current: datetime, data_dir: Path) -> str:
    pending = reminders.list_pending(data_dir, current)
    if not pending:
        return "예약된 알림이 없어요."
    lines = [f"- {timeparse.format_korean_datetime(r.due, current)}: {r.text}" for r in pending]
    return f"예약된 알림이 {len(pending)}개 있어요:\n" + "\n".join(lines)


# ---- 단위 변환 ----


def _convert(args: str, current: datetime, data_dir: Path) -> str:
    return units.reply(args)


# ---- 공휴일 / D-day ----


def _fmt_date(d: date) -> str:
    return f"{d.year}년 {d.month}월 {d.day}일({WEEKDAYS[d.weekday()]})"


def _holiday_next(args: str, current: datetime, data_dir: Path) -> str:
    from jev.skills import holidays

    today = current.date()
    try:
        found = holidays.next_holiday(today)
    except holidays.UnsupportedYearError as e:
        return str(e)
    if found is None:
        last = holidays.SUPPORTED_YEARS[-1]
        return f"{last}년까지의 공휴일만 알고 있어서, 다음 공휴일은 아직 알려드릴 수 없어요."
    day, name = found
    if day == today:
        return f"오늘({_fmt_date(day)})이 바로 {josa(name, '이에요', '예요')}!"
    days = (day - today).days
    return f"다음 공휴일은 {_fmt_date(day)} {josa(name, '이에요', '예요')}. {days}일 남았어요."


def _holiday_year(args: str, current: datetime, data_dir: Path) -> str:
    from jev.skills import holidays

    this_year = current.year
    named = {"올해": this_year, "내년": this_year + 1, "작년": this_year - 1}
    m = re.search(r"\d{4}", args)
    year = int(m.group()) if m else named.get(args.strip(), this_year)
    try:
        items = holidays.holidays_in_year(year)
    except holidays.UnsupportedYearError:
        first, last = holidays.SUPPORTED_YEARS[0], holidays.SUPPORTED_YEARS[-1]
        return f"{year}년 공휴일 정보는 아직 없어요. {first}~{last}년만 알려드릴 수 있어요."
    lines = [f"- {d.month}월 {d.day}일({WEEKDAYS[d.weekday()]}) {name}" for d, name in items]
    return f"{year}년 공휴일은 {len(items)}일이에요:\n" + "\n".join(lines)


def _holiday_check(args: str, current: datetime, data_dir: Path) -> str:
    from jev.skills import holidays

    word = args.strip() or "오늘"
    offset = {"오늘": 0, "내일": 1, "모레": 2}.get(word, 0)
    day = date.fromordinal(current.date().toordinal() + offset)
    try:
        name = holidays.holiday_name(day)
    except holidays.UnsupportedYearError as e:
        return str(e)
    if name:
        return f"네, {josa(word, '은', '는')} {josa(name, '이에요', '예요')}. ({_fmt_date(day)})"
    if day.weekday() >= 5:
        return f"{josa(word, '은', '는')} 공휴일은 아니지만 주말이에요. ({_fmt_date(day)})"
    return f"아니요, {josa(word, '은', '는')} 공휴일이 아니에요. ({_fmt_date(day)})"


def _parse_date(text: str, today: date) -> date | None:
    """'2026-12-25', '2026.12.25', '2026년 12월 25일', '12월 25일'(지났으면 내년)."""
    m = re.search(r"(\d{4})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})", text)
    try:
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", text)
        if not m:
            return None
        month, day = int(m.group(1)), int(m.group(2))
        target = date(today.year, month, day)
        return target if target >= today else date(today.year + 1, month, day)
    except ValueError:
        return None


def _dday(args: str, current: datetime, data_dir: Path) -> str:
    today = current.date()
    target = _parse_date(args, today)
    if target is None:
        return (
            "날짜를 이해하지 못했어요. '12월 25일까지 며칠'이나 'D-day 2026-12-25'처럼 말해 주세요."
        )
    days = (target - today).days
    if days == 0:
        return f"{_fmt_date(target)}은 바로 오늘이에요! (D-Day)"
    if days > 0:
        return f"{_fmt_date(target)}까지 {days}일 남았어요. (D-{days})"
    return f"{_fmt_date(target)}은 {-days}일 지났어요. (D+{-days})"


_Handler = Callable[[str, datetime, Path], str]
_HANDLERS: dict[str, _Handler] = {
    "memo_add": _memo_add,
    "memo_list": _memo_list,
    "memo_search": _memo_search,
    "memo_delete": _memo_delete,
    "remind_add": _remind_add,
    "remind_list": _remind_list,
    "convert": _convert,
    "holiday_next": _holiday_next,
    "holiday_year": _holiday_year,
    "holiday_check": _holiday_check,
    "dday": _dday,
}
