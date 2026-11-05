"""대한민국 공휴일(관공서의 공휴일) 데이터와 조회 함수.

외부 API 없이 동작하는 순수 데이터/순수 함수 모듈이다.

구성
----
* 양력 고정 공휴일(신정, 삼일절, 노동절, 어린이날, 현충일, 제헌절, 광복절, 개천절,
  한글날, 성탄절)은 계산한다. 노동절·제헌절은 2026년부터 공휴일이다.
* 음력 공휴일(설날 연휴, 부처님오신날, 추석 연휴)은 연도별 표(`_LUNAR`)에 명시한다.
* 대체공휴일은 발표된 표(`_SUBSTITUTES`)를 그대로 쓰고, 테스트에서
  규칙 기반 계산(`compute_substitutes`)과 일치하는지 교차 검증한다.
* 임시공휴일·선거일은 정부가 공식 지정한 것만 `_SPECIAL`에 넣는다. 이후 새로 지정되는
  임시공휴일이나 재·보궐 선거일 등은 빠져 있을 수 있다.

대체공휴일 규칙 (관공서의 공휴일에 관한 규정 제3조, 2026-05-01 시행 개정 포함)
------------------------------------------------------------------------------
* 설날·추석 연휴: 연휴가 일요일 또는 다른 공휴일과 겹치면 연휴 다음 첫 비공휴일.
* 삼일절·노동절·어린이날·부처님오신날·제헌절·광복절·개천절·한글날·성탄절:
  토요일·일요일 또는 다른 공휴일과 겹치면 그 다음 첫 비공휴일.
* 신정·현충일·선거일·임시공휴일은 대체공휴일 대상이 아니다.

출처
----
* 우주항공청(한국천문연구원) 월력요항
  - https://astro.kasi.re.kr/kor/life/post/calendarData?year=2026
  - https://astro.kasi.re.kr/kor/life/post/calendarData?year=2027
  - 2027년도 월력요항 보도(2026-06-29): https://www.segye.com/newsView/20260629506183 ,
    https://www.ytn.co.kr/_ln/0105_202606291128526819 ,
    https://www.heraldk.com/article/2026062816450881349
  - 2026년도 월력요항 보도(2025-06-30): https://www.segye.com/newsView/20250630506724
* 노동절·제헌절 공휴일 지정(인사혁신처 보도자료, 2026-04-28):
  https://www.korea.kr/briefing/pressReleaseView.do?newsId=156758983 ,
  https://law.go.kr/LSW/lsRvsRsnListP.do?lsId=002404&chrClsCd=010102
* 2025-01-27 임시공휴일 지정: https://shiftee.io/ko/blog/article/2025-lunar-new-year-temporary-holiday-faqs-and-pay-rules
* 2025-06-03 제21대 대통령선거 임시공휴일: https://www.tfmedia.co.kr/news/article.html?no=184713 ,
  https://www.news1.kr/politics/president/5746150
* 2026-06-03 제9회 전국동시지방선거: https://www.wikitree.co.kr/articles/1098048
* 2025-05-06 대체공휴일(어린이날·부처님오신날 중복):
  https://shiftee.io/ko/blog/article/2025-may-6-alternative-holiday-guidelines-for-hr
* 2025-10-10 임시공휴일은 지정되지 않음: https://biz.sbs.co.kr/amp/article/20000253637
* 2026-09-28 임시공휴일은 지정되지 않음, 추석 대체공휴일 없음:
  https://www.wikitree.co.kr/articles/1161815
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

__all__ = [
    "SUPPORTED_YEARS",
    "UnsupportedYearError",
    "compute_substitutes",
    "holiday_name",
    "holidays_in_year",
    "is_holiday",
    "is_weekend_or_holiday",
    "next_holiday",
]

SUPPORTED_YEARS: range = range(2025, 2028)

_SATURDAY = 5
_SUNDAY = 6


class UnsupportedYearError(ValueError):
    """공휴일 데이터가 없는 연도를 조회했을 때."""

    def __init__(self, year: int) -> None:
        first, last = SUPPORTED_YEARS[0], SUPPORTED_YEARS[-1]
        super().__init__(f"{year}년 공휴일 정보는 없어요. ({first}~{last}년만 지원)")
        self.year = year


# 음력 공휴일: (설날 당일, 부처님오신날, 추석 당일). 연휴는 당일 앞뒤 하루씩.
_LUNAR: dict[int, tuple[date, date, date]] = {
    2025: (date(2025, 1, 29), date(2025, 5, 5), date(2025, 10, 6)),
    2026: (date(2026, 2, 17), date(2026, 5, 24), date(2026, 9, 25)),
    2027: (date(2027, 2, 7), date(2027, 5, 13), date(2027, 9, 15)),
}

# 정부가 공식 지정한 임시공휴일·선거일 (대체공휴일 대상 아님).
_SPECIAL: dict[int, tuple[tuple[date, str], ...]] = {
    2025: (
        (date(2025, 1, 27), "임시공휴일"),
        (date(2025, 6, 3), "제21대 대통령선거"),
    ),
    2026: ((date(2026, 6, 3), "제9회 전국동시지방선거"),),
    # 2027년: 월력요항 발표(2026-06-29) 기준 지정된 임시공휴일·선거일 없음.
    2027: (),
}

# 발표된 대체공휴일 (월력요항 및 언론 보도 기준).
_SUBSTITUTES: dict[int, tuple[tuple[date, str], ...]] = {
    2025: (
        (date(2025, 3, 3), "대체공휴일(삼일절)"),
        # 어린이날과 부처님오신날이 5/5(월)에 겹쳐 생긴 대체공휴일. 자료에 따라
        # 어린이날 또는 부처님오신날의 대체공휴일로 표기가 갈려 둘 다 적는다.
        (date(2025, 5, 6), "대체공휴일(어린이날·부처님오신날)"),
        (date(2025, 10, 8), "대체공휴일(추석)"),
    ),
    2026: (
        (date(2026, 3, 2), "대체공휴일(삼일절)"),
        (date(2026, 5, 25), "대체공휴일(부처님오신날)"),
        (date(2026, 8, 17), "대체공휴일(광복절)"),
        (date(2026, 10, 5), "대체공휴일(개천절)"),
    ),
    2027: (
        (date(2027, 2, 9), "대체공휴일(설날)"),
        (date(2027, 5, 3), "대체공휴일(노동절)"),
        (date(2027, 7, 19), "대체공휴일(제헌절)"),
        (date(2027, 8, 16), "대체공휴일(광복절)"),
        (date(2027, 10, 4), "대체공휴일(개천절)"),
        (date(2027, 10, 11), "대체공휴일(한글날)"),
        (date(2027, 12, 27), "대체공휴일(성탄절)"),
    ),
}

# 토·일 또는 다른 공휴일과 겹치면 대체공휴일이 생기는 공휴일.
_WEEKEND_SUBSTITUTABLE = frozenset(
    {
        "삼일절",
        "노동절",
        "어린이날",
        "부처님오신날",
        "제헌절",
        "광복절",
        "개천절",
        "한글날",
        "성탄절",
    }
)


def _check_year(year: int) -> None:
    if year not in SUPPORTED_YEARS:
        raise UnsupportedYearError(year)


def _fixed_holidays(year: int) -> list[tuple[date, str]]:
    items = [
        (date(year, 1, 1), "신정"),
        (date(year, 3, 1), "삼일절"),
        (date(year, 5, 5), "어린이날"),
        (date(year, 6, 6), "현충일"),
        (date(year, 8, 15), "광복절"),
        (date(year, 10, 3), "개천절"),
        (date(year, 10, 9), "한글날"),
        (date(year, 12, 25), "성탄절"),
    ]
    if year >= 2026:  # 2026-05-01 시행 개정으로 공휴일 지정
        items += [(date(year, 5, 1), "노동절"), (date(year, 7, 17), "제헌절")]
    return items


def _lunar_holidays(year: int) -> list[tuple[date, str]]:
    seollal, buddha, chuseok = _LUNAR[year]
    one = timedelta(days=1)
    return [
        (seollal - one, "설날 연휴"),
        (seollal, "설날"),
        (seollal + one, "설날 연휴"),
        (buddha, "부처님오신날"),
        (chuseok - one, "추석 연휴"),
        (chuseok, "추석"),
        (chuseok + one, "추석 연휴"),
    ]


def _base_holidays(year: int) -> list[tuple[date, str]]:
    """대체공휴일을 제외한 공휴일 (같은 날 여러 개면 따로 들어 있음)."""
    return _fixed_holidays(year) + _lunar_holidays(year) + list(_SPECIAL[year])


def _group(items: Iterable[tuple[date, str]]) -> dict[date, list[str]]:
    grouped: dict[date, list[str]] = {}
    for d, name in items:
        grouped.setdefault(d, []).append(name)
    return grouped


def compute_substitutes(year: int) -> list[tuple[date, str]]:
    """대체공휴일 규칙으로 계산한 대체공휴일 목록 (발표 표 교차 검증용)."""
    _check_year(year)
    by_day = _group(_base_holidays(year))
    taken: set[date] = set(by_day)
    result: list[tuple[date, str]] = []

    def next_free(after: date) -> date:
        d = after + timedelta(days=1)
        while d.weekday() >= _SATURDAY or d in taken:
            d += timedelta(days=1)
        return d

    def add(after: date, label: str) -> None:
        d = next_free(after)
        taken.add(d)
        result.append((d, f"대체공휴일({label})"))

    seollal, _buddha, chuseok = _LUNAR[year]
    for label, center in (("설날", seollal), ("추석", chuseok)):
        days = [center + timedelta(days=k) for k in (-1, 0, 1)]
        # 연휴 중 일요일이거나 다른 공휴일과 겹친 날마다 하루씩.
        overlaps = sum(1 for d in days if d.weekday() == _SUNDAY or len(by_day[d]) > 1)
        for _ in range(overlaps):
            add(days[-1], label)

    for d in sorted(by_day):
        names = by_day[d]
        eligible = [n for n in names if n in _WEEKEND_SUBSTITUTABLE]
        if not eligible:
            continue
        count = len(names) - 1  # 같은 날 겹친 다른 공휴일 수
        if d.weekday() >= _SATURDAY:
            count += 1
        # 설·추석 연휴와 겹친 경우는 위에서 이미 하루 추가했으므로 중복 계산하지 않는다.
        if any(n.startswith(("설날", "추석")) for n in names):
            count -= 1
        for _ in range(max(count, 0)):
            add(d, "·".join(eligible))

    return sorted(result)


def holidays_in_year(year: int) -> list[tuple[date, str]]:
    """해당 연도의 공휴일을 날짜순으로. 같은 날 겹친 공휴일은 '·'로 합친다."""
    _check_year(year)
    by_day = _group([*_base_holidays(year), *_SUBSTITUTES[year]])
    return [(d, "·".join(by_day[d])) for d in sorted(by_day)]


def holiday_name(d: date) -> str | None:
    """공휴일이면 이름(예: '추석', '대체공휴일(어린이날)'), 아니면 None."""
    for day, name in holidays_in_year(d.year):
        if day == d:
            return name
    return None


def is_holiday(d: date) -> bool:
    return holiday_name(d) is not None


def is_weekend_or_holiday(d: date) -> bool:
    return d.weekday() >= _SATURDAY or is_holiday(d)


def next_holiday(on_or_after: date) -> tuple[date, str] | None:
    """해당 날짜 이후(당일 포함) 첫 공휴일. 지원 범위를 넘어가면 None."""
    if on_or_after.year > SUPPORTED_YEARS[-1]:
        return None
    _check_year(on_or_after.year)
    for year in range(on_or_after.year, SUPPORTED_YEARS[-1] + 1):
        for day, name in holidays_in_year(year):
            if day >= on_or_after:
                return day, name
    return None
