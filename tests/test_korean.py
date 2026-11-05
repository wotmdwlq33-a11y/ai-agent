from datetime import UTC, date, datetime

import pytest

from jev.korean import TIMEZONE, format_date, has_final_consonant, josa, localize


@pytest.mark.parametrize(
    "word, expected",
    [
        ("성탄절", True),
        ("추석", True),
        ("어린이날", True),
        ("설날 연휴", False),
        ("마일", True),
        ("피트", False),
        ("km", False),
        ("대체공휴일(성탄절)", True),
    ],
)
def test_has_final_consonant(word, expected):
    assert has_final_consonant(word) is expected


def test_josa():
    assert josa("성탄절", "이에요", "예요") == "성탄절이에요"
    assert josa("노동절·제헌절", "은", "는") == "노동절·제헌절은"
    assert josa("피트", "은", "는") == "피트는"


def test_localize_and_format_date():
    naive = datetime(2026, 11, 5, 9, 0)
    assert localize(naive).tzinfo is TIMEZONE
    utc = datetime(2026, 11, 5, 0, 0, tzinfo=UTC)
    assert localize(utc).hour == 9
    assert format_date(date(2026, 12, 25)) == "2026년 12월 25일(금)"
