from datetime import datetime, timedelta

import pytest

from jev.skills.timeparse import (
    TIMEZONE,
    find_korean_time,
    format_korean_datetime,
    leading_time,
    parse_korean_time,
)

# 2026-11-05 (목) 10:00
NOW = datetime(2026, 11, 5, 10, 0, tzinfo=TIMEZONE)


def at(month, day, hour, minute=0, second=0, year=2026):
    return datetime(year, month, day, hour, minute, second, tzinfo=TIMEZONE)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("10분 뒤", NOW + timedelta(minutes=10)),
        ("10분 후", NOW + timedelta(minutes=10)),
        ("2시간 뒤", NOW + timedelta(hours=2)),
        ("1시간 30분 뒤", NOW + timedelta(hours=1, minutes=30)),
        ("1시간 반 뒤", NOW + timedelta(hours=1, minutes=30)),
        ("30초 뒤", NOW + timedelta(seconds=30)),
        ("3일 뒤", NOW + timedelta(days=3)),
        ("2주 후", NOW + timedelta(weeks=2)),
        ("10분 있다가", NOW + timedelta(minutes=10)),
    ],
)
def test_relative(text, expected):
    assert parse_korean_time(text, NOW) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("내일 9시", at(11, 6, 9)),
        ("모레 오후 3시", at(11, 7, 15)),
        ("오늘 저녁 7시 30분", at(11, 5, 19, 30)),
        ("오후 3시", at(11, 5, 15)),
        ("9시 반", at(11, 5, 21, 30)),  # 오전 9시 반은 지났으니 오후
        ("다음 주 월요일 10시", at(11, 9, 10)),
        ("담주 월요일 10시", at(11, 9, 10)),
        ("다다음 주 화요일 오전 8시", at(11, 17, 8)),
        ("이번 주 금요일 오후 2시", at(11, 6, 14)),
        ("3일 뒤 오후 3시", at(11, 8, 15)),
        ("14:30", at(11, 5, 14, 30)),
        ("오전 11시", at(11, 5, 11)),
        ("아침 7시", at(11, 6, 7)),  # 오늘 아침 7시는 지났으니 내일
        ("내일 아침 7시", at(11, 6, 7)),
        ("낮 12시", at(11, 5, 12)),
        ("오후 12시", at(11, 5, 12)),
        ("오전 12시", at(11, 6, 0)),
        ("밤 11시", at(11, 5, 23)),
    ],
)
def test_absolute(text, expected):
    assert parse_korean_time(text, NOW) == expected


def test_results_are_seoul_aware():
    result = parse_korean_time("내일 9시", NOW)
    assert result is not None
    assert result.tzinfo is not None
    assert result.utcoffset() == timedelta(hours=9)


class TestBareHourRule:
    """오전/오후 없는 1~11시: 오늘 오전 → 오늘 오후 → 내일 오전 순으로 아직 안 지난 것."""

    def test_morning_still_ahead(self):
        early = at(11, 5, 7)
        assert parse_korean_time("9시", early) == at(11, 5, 9)

    def test_morning_passed_pm_ahead(self):
        assert parse_korean_time("3시", NOW) == at(11, 5, 15)

    def test_both_passed_goes_to_tomorrow_morning(self):
        late = at(11, 5, 22)
        assert parse_korean_time("9시", late) == at(11, 6, 9)

    def test_exactly_now_is_not_ahead(self):
        assert parse_korean_time("10시", NOW) == at(11, 5, 22)

    def test_24h_hours_are_literal(self):
        assert parse_korean_time("15시", NOW) == at(11, 5, 15)
        assert parse_korean_time("12시", NOW) == at(11, 5, 12)
        assert parse_korean_time("0시", NOW) == at(11, 6, 0)

    def test_today_keeps_today_even_if_passed(self):
        late = at(11, 5, 22)
        assert parse_korean_time("오늘 9시", late) == at(11, 5, 21)
        assert parse_korean_time("오늘 11시", NOW) == at(11, 5, 11)

    def test_other_day_small_hours_are_pm(self):
        assert parse_korean_time("내일 3시", NOW) == at(11, 6, 15)
        assert parse_korean_time("내일 6시", NOW) == at(11, 6, 18)
        assert parse_korean_time("내일 7시", NOW) == at(11, 6, 7)


class TestNight:
    def test_night_12_is_next_midnight(self):
        assert parse_korean_time("오늘 밤 12시", NOW) == at(11, 6, 0)
        assert parse_korean_time("밤 12시", NOW) == at(11, 6, 0)
        assert parse_korean_time("내일 밤 12시", NOW) == at(11, 7, 0)

    def test_night_small_hours_are_next_early_morning(self):
        assert parse_korean_time("오늘 밤 1시", NOW) == at(11, 6, 1)

    def test_night_without_day_is_next_occurrence(self):
        just_after_midnight = at(11, 6, 0, 30)
        assert parse_korean_time("밤 1시", just_after_midnight) == at(11, 6, 1)

    def test_evening_12(self):
        assert parse_korean_time("저녁 12시", NOW) == at(11, 6, 0)


def test_weekday_today_rolls_to_next_week_when_passed():
    # 오늘은 목요일 10시
    assert parse_korean_time("목요일 9시", NOW) == at(11, 12, 9)
    assert parse_korean_time("목요일 11시", NOW) == at(11, 5, 11)
    assert parse_korean_time("월요일 10시", NOW) == at(11, 9, 10)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "회의",
        "내일",
        "다음 주 월요일",
        "25시",
        "오후 13시 70분",
        "9시 70분",
        "오전 15시",
        "0분 뒤",
    ],
)
def test_unparseable(text):
    assert parse_korean_time(text, NOW) is None


def test_find_reports_span():
    text = "내일 9시에 병원 가기"
    found = find_korean_time(text, NOW)
    assert found is not None
    assert text[found.start : found.end] == "내일 9시"
    assert found.when == at(11, 6, 9)


def test_find_prefers_earliest_and_longest():
    found = find_korean_time("회의를 3일 뒤 9시에", NOW)
    assert found is not None
    assert found.when == at(11, 8, 9)


def test_hours_word_is_not_clock():
    # "1시간"의 "1시"를 시각으로 읽으면 안 된다
    assert parse_korean_time("1시간 뒤", NOW) == NOW + timedelta(hours=1)


def test_naive_now_is_treated_as_seoul():
    naive = datetime(2026, 11, 5, 10, 0)
    assert parse_korean_time("10분 뒤", naive) == NOW + timedelta(minutes=10)


def test_month_rollover():
    eom = at(12, 31, 23)
    assert parse_korean_time("내일 9시", eom) == at(1, 1, 9, year=2027)


def test_leading_time():
    assert leading_time("10분 뒤에 회의") == (5, True)
    assert leading_time("내일 9시에 병원") == (len("내일 9시"), False)
    assert leading_time("회의 내일 9시") is None
    assert leading_time("내일 날씨") is None


@pytest.mark.parametrize(
    "when, expected",
    [
        (at(11, 5, 10, 10), "오늘 오전 10시 10분"),
        (at(11, 6, 9), "내일 오전 9시"),
        (at(11, 7, 15), "모레 오후 3시"),
        (at(11, 9, 0, 0, 30), "11월 9일(월) 오전 12시 30초"),
        (at(1, 2, 12, year=2027), "2027년 1월 2일(토) 오후 12시"),
    ],
)
def test_format_korean_datetime(when, expected):
    assert format_korean_datetime(when, NOW) == expected


def test_relative_minutes_round_up_to_whole_minute():
    from datetime import datetime, timedelta

    from jev.skills.timeparse import TIMEZONE, parse_korean_time

    now = datetime(2026, 11, 5, 12, 50, 57, 123, tzinfo=TIMEZONE)
    assert parse_korean_time("10분 뒤", now) == datetime(2026, 11, 5, 13, 1, tzinfo=TIMEZONE)
    # 초를 말하면 그대로 더한다
    assert parse_korean_time("30초 뒤", now) == now + timedelta(seconds=30)


class TestCalendarDates:
    def test_month_day(self):
        assert parse_korean_time("12월 25일 9시", NOW) == at(12, 25, 9)
        assert parse_korean_time("12월 25일 오후 3시", NOW) == at(12, 25, 15)
        assert parse_korean_time("12월 25일 3시", NOW) == at(12, 25, 15)  # 다른 날 1~6시는 오후

    def test_month_day_passed_rolls_to_next_year(self):
        assert parse_korean_time("3월 1일 10시", NOW) == at(3, 1, 10, year=2027)
        # 오늘 날짜인데 시각이 지났으면 내년
        assert parse_korean_time("11월 5일 9시", NOW) == at(11, 5, 9, year=2027)
        assert parse_korean_time("11월 5일 오후 9시", NOW) == at(11, 5, 21)

    def test_explicit_year_does_not_roll(self):
        assert parse_korean_time("2026년 3월 1일 10시", NOW) == at(3, 1, 10)
        assert parse_korean_time("2027년 1월 2일 오전 8시", NOW) == at(1, 2, 8, year=2027)

    def test_next_and_this_month(self):
        assert parse_korean_time("다음 달 3일 10시", NOW) == at(12, 3, 10)
        assert parse_korean_time("담달 3일 10시", NOW) == at(12, 3, 10)
        assert parse_korean_time("이번 달 20일 오후 2시", NOW) == at(11, 20, 14)
        december = at(12, 10, 9)
        assert parse_korean_time("다음 달 3일 10시", december) == at(1, 3, 10, year=2027)

    @pytest.mark.parametrize("text", ["2월 30일 9시", "13월 1일 9시", "다음 달 31일 9시"])
    def test_invalid_dates(self, text):
        # '다음 달 31일'은 10월 기준(→ 11월 31일)으로 확인한다
        now = at(10, 5, 10) if text.startswith("다음 달") else NOW
        assert parse_korean_time(text, now) is None

    def test_span_covers_date(self):
        text = "12월 25일 9시에 파티"
        found = find_korean_time(text, NOW)
        assert found is not None
        assert text[found.start : found.end] == "12월 25일 9시"


def test_pm_zero_is_noon():
    assert parse_korean_time("오후 0시 30분", NOW) == at(11, 5, 12, 30)
    assert parse_korean_time("낮 0시", NOW) == at(11, 5, 12)
    assert parse_korean_time("내일 오후 0시 30분", NOW) == at(11, 6, 12, 30)
    assert parse_korean_time("오늘 밤 0시", NOW) == at(11, 6, 0)
    assert parse_korean_time("오전 0시 30분", NOW) == at(11, 6, 0, 30)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("정오", (2026, 11, 5, 12, 0)),
        ("내일 정오", (2026, 11, 6, 12, 0)),
        ("12월 25일 정오", (2026, 12, 25, 12, 0)),
        ("자정", (2026, 11, 6, 0, 0)),
        ("오늘 자정", (2026, 11, 6, 0, 0)),
        ("내일 자정", (2026, 11, 7, 0, 0)),
    ],
)
def test_noon_and_midnight_words(text, expected):
    assert parse_korean_time(text, NOW) == datetime(*expected, tzinfo=TIMEZONE)


def test_noon_already_passed_means_tomorrow():
    after_noon = at(11, 5, 13)
    assert parse_korean_time("정오", after_noon) == at(11, 6, 12)
