"""한국어 시간 표현을 Asia/Seoul 시각으로 바꾼다 (규칙 기반, API 호출 없음).

지원하는 표현
-------------
* 상대 시간: "30초 뒤", "10분 후", "2시간 뒤", "1시간 30분 뒤", "1시간 반 뒤",
  "3일 뒤", "2주 후", "10분 있다가"
* 날짜 + 시각: "오늘/내일/모레/글피", "N일 뒤", "월요일", "이번 주 금요일",
  "다음 주(담주) 월요일", "다다음 주 화요일", "12월 25일", "2027년 1월 2일",
  "다음 달(담달) 3일", "이번 달 20일" 뒤에 시각이 붙은 것
* 시각: "9시", "9시 반", "7시 30분", "14:30", 앞에 오전/오후 등의 때를 붙일 수 있음

날짜 단어만 있고 시각이 없으면("내일", "다음 주 월요일") 인식하지 않는다.
"아침에", "저녁에"처럼 숫자 시각이 없는 때 표현도 인식하지 않는다.
"정오"(낮 12시)와 "자정"(밤 12시, 즉 다음 날 0시)은 인식한다.

시각 해석 규칙
--------------
* 새벽/아침/오전 = 오전. "오전 12시" = 0시.
* 오후/낮/점심/저녁 = 오후 (1~11시에 12를 더함). "오후 12시"·"오후 0시" = 12시(정오).
* 밤 6~11시 = 18~23시. 밤 12시 = 그 날이 끝나는 자정, 즉 다음 날 0시.
  밤 1~5시 = 다음 날 새벽 1~5시 ("오늘 밤 1시" = 내일 01:00).
  "저녁 12시", "밤 0시", "저녁 0시"도 밤 12시와 같이 다음 날 0시로 본다.
* 날짜 없이 시각만 있으면 지금 이후 가장 가까운 그 시각(이미 지났으면 내일).
  "밤 12시", "밤 1시"도 이 경우엔 '다음에 오는 0시/1시'다.
* 오전/오후 없는 "N시":
  - 0시, 12~23시는 그대로 (12시 = 정오).
  - 날짜 없이 1~11시면: 오늘 오전 N시가 아직 안 지났으면 그것, 지났으면 오늘 오후 N시,
    그것도 지났으면 내일 오전 N시. (오전 10시에 "3시" → 오늘 15시)
  - "오늘 N시"(1~11)면: 오전 N시가 안 지났으면 오전, 아니면 오후 (지났어도 오늘).
  - 다른 날짜가 붙은 1~11시("내일 3시", "다음 주 월요일 10시"): 1~6시는 오후,
    7~11시는 오전으로 본다. 새벽 약속은 드물기 때문.
* 요일만("금요일 3시"): 이번 주 그 요일이 오늘 이후면 그 날, 오늘이 그 요일인데
  시각이 이미 지났거나 이미 지난 요일이면 다음 주.
* 연도 없는 "M월 D일": 그 시각이 이미 지났으면 내년. 연도를 쓰거나 "이번 달 D일"이면
  지났어도 그대로 둔다. 없는 날짜("2월 30일", "다음 달 31일"이 없는 달)는 인식하지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from jev.korean import TIMEZONE, WEEKDAYS, localize

_AM = {"새벽", "아침", "오전"}
_PM = {"오후", "낮", "점심", "저녁"}

_DAY = (
    r"(?<!\d)(?:(?P<year>\d{4})\s*년\s*)?(?P<month>\d{1,2})\s*월\s*(?P<mday>\d{1,2})\s*일(?:에|날)?"
    r"|(?P<mrel>다음\s*달|담달|이번\s*달)\s*(?P<mday2>\d{1,2})\s*일(?:에|날)?"
    r"|(?P<day>오늘|내일|모레|글피)"
    r"|(?<!\d)(?P<ndays>\d{1,3})\s*일\s*(?:뒤|후)(?:에)?"
    r"|(?:(?P<week>다다음\s*주|다음\s*주|담주|이번\s*주)\s*)?(?P<wd>[월화수목금토일])요일(?:에|날)?"
)
_PERIOD = r"(?P<period>새벽|아침|오전|낮|점심|오후|저녁|밤)"
_CLOCK = (
    r"(?<!\d)(?P<hour>\d{1,2})\s*시(?!\s*간)"
    r"(?:\s*(?P<half>반)(?=$|\s|에|까지|부터|[,.!?？])|\s*(?P<minute>\d{1,2})\s*분)?"
    r"|(?<!\d)(?P<hh>\d{1,2}):(?P<mm>\d{2})(?!\d)"
    r"|(?P<named>정오|자정)"
)
_ABS_RE = re.compile(rf"(?:(?:{_DAY})\s*)?(?:{_PERIOD}\s*)?(?:{_CLOCK})")
_REL_RE = re.compile(
    r"(?<!\d)(?=\d)"
    r"(?:(?P<w>\d{1,3})\s*주\s*)?"
    r"(?:(?P<d>\d{1,3})\s*일\s*)?"
    r"(?:(?P<h>\d{1,3})\s*시간\s*(?P<hhalf>반\s*)?)?"
    r"(?:(?P<m>\d{1,4})\s*분\s*)?"
    r"(?:(?P<s>\d{1,5})\s*초\s*)?"
    r"(?:뒤|후|있다가|지나서)"
)


@dataclass(frozen=True)
class TimeMatch:
    """찾은 시각과, 원문에서 그 표현이 차지한 범위 text[start:end]."""

    when: datetime
    start: int
    end: int


def _at(d: date, hour: int, minute: int) -> datetime:
    return datetime.combine(d, time(hour, minute), tzinfo=TIMEZONE)


def _apply_period(hour: int, period: str) -> tuple[int, int] | None:
    """(24시간제 시, 날짜 이동)을 돌려준다. 말이 안 되는 조합이면 None."""
    if hour > 23:
        return None
    if period in _AM:
        if hour > 12:
            return None
        return (0 if hour == 12 else hour), 0
    if hour >= 13:  # "오후 15시"처럼 24시간제를 같이 쓴 경우는 그대로
        return hour, 0
    if hour == 0:  # 오후 0시 = 정오, 저녁/밤 0시 = 다음 날 0시
        return (12, 0) if period in ("오후", "낮", "점심") else (0, 1)
    if period in _PM:
        if hour == 12:
            return (0, 1) if period == "저녁" else (12, 0)
        return hour + 12, 0
    # 밤
    if hour == 12:
        return 0, 1
    if hour <= 5:
        return hour, 1
    return hour + 12, 0


def _resolve_relative(m: re.Match[str], now: datetime) -> datetime | None:
    def num(name: str) -> int:
        value = m.group(name)
        return int(value) if value else 0

    delta = timedelta(
        weeks=num("w"),
        days=num("d"),
        hours=num("h"),
        minutes=num("m") + (30 if m.group("hhalf") else 0),
        seconds=num("s"),
    )
    if delta <= timedelta(0):
        return None
    base = now
    if not m.group("s") and (now.second or now.microsecond):
        # 초 단위를 말하지 않았으면 분 단위로 올림한다 ("10분 뒤" → 정각 분, 초 표시 없음)
        base = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    try:
        return base + delta
    except OverflowError:
        return None


def _explicit_day(m: re.Match[str], today: date) -> tuple[date, str | None] | None:
    """(날짜, 지났을 때 넘길 단위 "week"/"year"/None). 날짜가 없으면 None.

    없는 날짜(2월 30일 등)면 ValueError.
    """
    if m.group("month"):
        year = m.group("year")
        when = date(int(year) if year else today.year, int(m.group("month")), int(m.group("mday")))
        return when, None if year else "year"
    if m.group("mrel"):
        y, mo = today.year, today.month
        if re.sub(r"\s+", "", m.group("mrel")) != "이번달":
            y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
        return date(y, mo, int(m.group("mday2"))), None
    if m.group("day"):
        offset = {"오늘": 0, "내일": 1, "모레": 2, "글피": 3}[m.group("day")]
        return today + timedelta(days=offset), None
    if m.group("ndays"):
        return today + timedelta(days=int(m.group("ndays"))), None
    if m.group("wd"):
        target = WEEKDAYS.index(m.group("wd"))
        week = re.sub(r"\s+", "", m.group("week") or "")
        if not week:
            return today + timedelta(days=(target - today.weekday()) % 7), "week"
        monday = today - timedelta(days=today.weekday())
        weeks_ahead = {"이번주": 0, "다음주": 1, "담주": 1, "다다음주": 2}[week]
        return monday + timedelta(weeks=weeks_ahead, days=target), None
    return None


def _resolve_absolute(m: re.Match[str], now: datetime) -> datetime | None:
    named = m.group("named")
    period = m.group("period")
    if named:
        # 정오 = 낮 12시, 자정 = "밤 12시"와 같이 그 날이 끝나는 0시(다음 날 0시)
        hour, minute = 12, 0
        period = "밤" if named == "자정" else None
    elif m.group("hour") is not None:
        hour = int(m.group("hour"))
        minute = 30 if m.group("half") else int(m.group("minute") or 0)
    else:
        hour, minute = int(m.group("hh")), int(m.group("mm"))
    if hour > 23 or minute > 59:
        return None

    today = now.date()
    try:
        day = _explicit_day(m, today)
    except ValueError:
        return None

    if period:
        converted = _apply_period(hour, period)
        if converted is None:
            return None
        hour24, shift = converted
        if day is None:
            candidate = _at(today, hour24, minute)
            return candidate if candidate > now else candidate + timedelta(days=1)
    elif day is None:
        if 1 <= hour <= 11:
            for h in (hour, hour + 12):
                candidate = _at(today, h, minute)
                if candidate > now:
                    return candidate
            return _at(today + timedelta(days=1), hour, minute)
        candidate = _at(today, hour, minute)
        return candidate if candidate > now else candidate + timedelta(days=1)
    else:
        hour24, shift = hour, 0
        if 1 <= hour <= 11:
            if m.group("day") == "오늘":
                am = _at(today, hour, minute)
                return am if am > now else _at(today, hour + 12, minute)
            if hour <= 6:
                hour24 = hour + 12

    assert day is not None  # 날짜가 없는 경우는 위에서 모두 돌려줬다
    target, roll = day
    candidate = _at(target + timedelta(days=shift), hour24, minute)
    if candidate <= now:
        if roll == "week":
            candidate += timedelta(weeks=1)
        elif roll == "year":
            try:
                target = target.replace(year=target.year + 1)
            except ValueError:  # 2월 29일
                return None
            candidate = _at(target + timedelta(days=shift), hour24, minute)
    return candidate


def find_korean_time(text: str, now: datetime) -> TimeMatch | None:
    """text 안에서 처음 나오는 (해석 가능한) 시간 표현을 찾는다.

    같은 위치에서 여러 해석이 가능하면 더 긴 표현을 쓴다 ("3일 뒤 9시" > "3일 뒤").
    """
    now = localize(now)
    found: list[TimeMatch] = []
    for regex, resolve in ((_ABS_RE, _resolve_absolute), (_REL_RE, _resolve_relative)):
        for m in regex.finditer(text):
            when = resolve(m, now)
            if when is not None:
                found.append(TimeMatch(when, m.start(), m.end()))
                break
    if not found:
        return None
    return min(found, key=lambda t: (t.start, -t.end))


def parse_korean_time(text: str, now: datetime) -> datetime | None:
    """text 안의 시간 표현을 Asia/Seoul 시각으로 바꾼다. 못 찾으면 None."""
    found = find_korean_time(text, now)
    return found.when if found else None


def has_time_expression(text: str) -> bool:
    """text 어딘가에 시간 표현 모양이 있는지 (값이 맞는지는 따지지 않음). 라우터가 쓴다."""
    return bool(_ABS_RE.search(text) or _REL_RE.search(text))


def leading_time(text: str) -> tuple[int, bool] | None:
    """text가 시간 표현으로 시작하면 (끝 위치, 상대 시간인지)를 돌려준다.

    값이 맞는지(예: 25시)는 따지지 않고 모양만 본다. 라우터가 쓴다.
    """
    stripped = len(text) - len(text.lstrip())
    candidates = [
        (m.end(), relative)
        for regex, relative in ((_ABS_RE, False), (_REL_RE, True))
        if (m := regex.match(text, stripped))
    ]
    return max(candidates) if candidates else None


def format_korean_datetime(when: datetime, now: datetime) -> str:
    """예: "오늘 오후 3시 10분", "내일 오전 9시", "11월 9일(월) 오전 10시"."""
    when, now = localize(when), localize(now)
    days = (when.date() - now.date()).days
    named = {-1: "어제", 0: "오늘", 1: "내일", 2: "모레"}
    if days in named:
        day = named[days]
    else:
        day = f"{when.month}월 {when.day}일({WEEKDAYS[when.weekday()]})"
        if when.year != now.year:
            day = f"{when.year}년 {day}"
    ampm = "오전" if when.hour < 12 else "오후"
    text = f"{day} {ampm} {when.hour % 12 or 12}시"
    if when.minute:
        text += f" {when.minute}분"
    if when.second:
        text += f" {when.second}초"
    return text
