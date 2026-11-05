from datetime import date

import pytest

from jev.skills import holidays as h
from jev.skills.holidays import (
    SUPPORTED_YEARS,
    UnsupportedYearError,
    compute_substitutes,
    holiday_name,
    holidays_in_year,
    is_holiday,
    is_weekend_or_holiday,
    next_holiday,
)

EXPECTED: dict[int, list[tuple[date, str]]] = {
    2025: [
        (date(2025, 1, 1), "신정"),
        (date(2025, 1, 27), "임시공휴일"),
        (date(2025, 1, 28), "설날 연휴"),
        (date(2025, 1, 29), "설날"),
        (date(2025, 1, 30), "설날 연휴"),
        (date(2025, 3, 1), "삼일절"),
        (date(2025, 3, 3), "대체공휴일(삼일절)"),
        (date(2025, 5, 5), "어린이날·부처님오신날"),
        (date(2025, 5, 6), "대체공휴일(어린이날·부처님오신날)"),
        (date(2025, 6, 3), "제21대 대통령선거"),
        (date(2025, 6, 6), "현충일"),
        (date(2025, 8, 15), "광복절"),
        (date(2025, 10, 3), "개천절"),
        (date(2025, 10, 5), "추석 연휴"),
        (date(2025, 10, 6), "추석"),
        (date(2025, 10, 7), "추석 연휴"),
        (date(2025, 10, 8), "대체공휴일(추석)"),
        (date(2025, 10, 9), "한글날"),
        (date(2025, 12, 25), "성탄절"),
    ],
    2026: [
        (date(2026, 1, 1), "신정"),
        (date(2026, 2, 16), "설날 연휴"),
        (date(2026, 2, 17), "설날"),
        (date(2026, 2, 18), "설날 연휴"),
        (date(2026, 3, 1), "삼일절"),
        (date(2026, 3, 2), "대체공휴일(삼일절)"),
        (date(2026, 5, 1), "노동절"),
        (date(2026, 5, 5), "어린이날"),
        (date(2026, 5, 24), "부처님오신날"),
        (date(2026, 5, 25), "대체공휴일(부처님오신날)"),
        (date(2026, 6, 3), "제9회 전국동시지방선거"),
        (date(2026, 6, 6), "현충일"),
        (date(2026, 7, 17), "제헌절"),
        (date(2026, 8, 15), "광복절"),
        (date(2026, 8, 17), "대체공휴일(광복절)"),
        (date(2026, 9, 24), "추석 연휴"),
        (date(2026, 9, 25), "추석"),
        (date(2026, 9, 26), "추석 연휴"),
        (date(2026, 10, 3), "개천절"),
        (date(2026, 10, 5), "대체공휴일(개천절)"),
        (date(2026, 10, 9), "한글날"),
        (date(2026, 12, 25), "성탄절"),
    ],
    2027: [
        (date(2027, 1, 1), "신정"),
        (date(2027, 2, 6), "설날 연휴"),
        (date(2027, 2, 7), "설날"),
        (date(2027, 2, 8), "설날 연휴"),
        (date(2027, 2, 9), "대체공휴일(설날)"),
        (date(2027, 3, 1), "삼일절"),
        (date(2027, 5, 1), "노동절"),
        (date(2027, 5, 3), "대체공휴일(노동절)"),
        (date(2027, 5, 5), "어린이날"),
        (date(2027, 5, 13), "부처님오신날"),
        (date(2027, 6, 6), "현충일"),
        (date(2027, 7, 17), "제헌절"),
        (date(2027, 7, 19), "대체공휴일(제헌절)"),
        (date(2027, 8, 15), "광복절"),
        (date(2027, 8, 16), "대체공휴일(광복절)"),
        (date(2027, 9, 14), "추석 연휴"),
        (date(2027, 9, 15), "추석"),
        (date(2027, 9, 16), "추석 연휴"),
        (date(2027, 10, 3), "개천절"),
        (date(2027, 10, 4), "대체공휴일(개천절)"),
        (date(2027, 10, 9), "한글날"),
        (date(2027, 10, 11), "대체공휴일(한글날)"),
        (date(2027, 12, 25), "성탄절"),
        (date(2027, 12, 27), "대체공휴일(성탄절)"),
    ],
}


def test_supported_years() -> None:
    assert list(SUPPORTED_YEARS) == [2025, 2026, 2027]
    assert set(EXPECTED) == set(SUPPORTED_YEARS)


@pytest.mark.parametrize("year", list(SUPPORTED_YEARS))
def test_full_year_table(year: int) -> None:
    assert holidays_in_year(year) == EXPECTED[year]


@pytest.mark.parametrize("year", list(SUPPORTED_YEARS))
def test_sorted_and_unique(year: int) -> None:
    days = [d for d, _ in holidays_in_year(year)]
    assert days == sorted(days)
    assert len(days) == len(set(days))
    assert all(d.year == year for d in days)


@pytest.mark.parametrize("year", list(SUPPORTED_YEARS))
def test_rule_based_substitutes_match_published(year: int) -> None:
    assert compute_substitutes(year) == list(h._SUBSTITUTES[year])


@pytest.mark.parametrize(
    "d, name",
    [
        (date(2025, 10, 6), "추석"),
        (date(2025, 1, 28), "설날 연휴"),
        (date(2025, 3, 3), "대체공휴일(삼일절)"),
        (date(2025, 10, 8), "대체공휴일(추석)"),
        (date(2026, 5, 25), "대체공휴일(부처님오신날)"),
        (date(2026, 7, 17), "제헌절"),
        (date(2027, 2, 9), "대체공휴일(설날)"),
        (date(2027, 12, 27), "대체공휴일(성탄절)"),
    ],
)
def test_holiday_name(d: date, name: str) -> None:
    assert holiday_name(d) == name
    assert is_holiday(d)


@pytest.mark.parametrize(
    "d",
    [
        date(2025, 1, 31),  # 금요일, 임시공휴일 아님
        date(2025, 5, 1),  # 노동절은 2026년부터 공휴일
        date(2025, 7, 17),  # 제헌절은 2026년부터 공휴일
        date(2025, 10, 10),  # 임시공휴일 지정 안 됨
        date(2026, 6, 8),  # 현충일(토)은 대체공휴일 없음
        date(2026, 9, 28),  # 추석 연휴가 토요일과 겹쳐도 대체공휴일 없음
        date(2026, 11, 5),
        date(2027, 6, 7),  # 현충일(일)도 대체공휴일 없음
    ],
)
def test_non_holidays(d: date) -> None:
    assert holiday_name(d) is None
    assert not is_holiday(d)


def test_weekend_or_holiday() -> None:
    assert is_weekend_or_holiday(date(2026, 11, 7))  # 토
    assert is_weekend_or_holiday(date(2026, 10, 9))  # 한글날(금)
    assert not is_weekend_or_holiday(date(2026, 11, 5))  # 목


def test_next_holiday() -> None:
    assert next_holiday(date(2026, 10, 9)) == (date(2026, 10, 9), "한글날")
    assert next_holiday(date(2026, 10, 10)) == (date(2026, 12, 25), "성탄절")


def test_next_holiday_crosses_year_boundary() -> None:
    assert next_holiday(date(2025, 12, 26)) == (date(2026, 1, 1), "신정")
    assert next_holiday(date(2026, 12, 26)) == (date(2027, 1, 1), "신정")


def test_next_holiday_beyond_data() -> None:
    assert next_holiday(date(2027, 12, 28)) is None
    assert next_holiday(date(2030, 1, 1)) is None


@pytest.mark.parametrize("year", [2024, 2028])
def test_unsupported_year_raises(year: int) -> None:
    with pytest.raises(UnsupportedYearError):
        holidays_in_year(year)
    with pytest.raises(UnsupportedYearError):
        holiday_name(date(year, 1, 1))
    with pytest.raises(ValueError):
        compute_substitutes(year)


def test_next_holiday_before_data_raises() -> None:
    with pytest.raises(UnsupportedYearError):
        next_holiday(date(2024, 12, 31))
