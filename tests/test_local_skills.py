from datetime import date, datetime, timedelta

import pytest

from jev import local_skills
from jev.router import route
from jev.skills import reminders

NOW = datetime(2026, 11, 5, 10, 0, tzinfo=local_skills.TIMEZONE)  # 목요일


def say(text, data_dir, current=NOW):
    r = route(text)
    assert r.target == "local", text
    assert r.skill is not None
    return local_skills.run(r.skill, current, text=text, data_dir=data_dir)


def test_time_date_help_unchanged():
    assert local_skills.run("time", NOW) == "지금은 10시 00분이에요."
    assert local_skills.run("date", NOW) == "오늘은 2026년 11월 05일 목요일이에요."
    help_text = local_skills.run("help", NOW)
    for word in ("메모", "알려줘", "마일", "공휴일", "D-day"):
        assert word in help_text


def test_unknown_skill():
    with pytest.raises(ValueError):
        local_skills.run("nope", NOW, text="", data_dir=None)


def test_default_data_dir():
    assert local_skills.default_data_dir().name == ".jev"


def test_memo_flow(tmp_path):
    assert say("메모 목록", tmp_path).startswith("저장된 메모가 없어요")
    assert say("메모: 우유 사기", tmp_path) == "메모했어요 (#1): 우유 사기"
    assert say("빵 사기 메모해줘", tmp_path) == "메모했어요 (#2): 빵 사기"
    listing = say("메모 보여줘", tmp_path)
    assert "메모가 2개 있어요" in listing
    assert "#1 우유 사기 (11월 5일)" in listing
    assert "#1 우유 사기" in say("메모 검색 우유", tmp_path)
    assert "없어요" in say("메모 검색 라면", tmp_path)
    assert say("메모 삭제 1", tmp_path) == "#1 메모를 지웠어요: 우유 사기"
    assert "없어요" in say("메모 삭제 1", tmp_path)
    assert "무엇을 메모할까요" in say("메모해줘", tmp_path)


def test_memo_errors_are_friendly(tmp_path):
    assert "너무 길어요" in say("메모: " + "가" * 1001, tmp_path)
    (tmp_path / "memos.json").write_text("oops", encoding="utf-8")
    assert "손상" in say("메모 목록", tmp_path)


def test_memo_list_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(local_skills, "MEMO_LIST_LIMIT", 2)
    for i in range(3):
        say(f"메모: 할 일 {i}", tmp_path)
    listing = say("메모 목록", tmp_path)
    assert "최근 2개만" in listing
    assert "할 일 0" not in listing


def test_run_accepts_route_args_as_text(tmp_path):
    # assistant가 원문 대신 Route.args를 넘겨도 동작한다
    assert local_skills.run("memo_add", NOW, text="우유 사기", data_dir=tmp_path).endswith(
        "우유 사기"
    )
    assert "10킬로미터" in local_skills.run(
        "convert", NOW, text="10km는 몇 마일", data_dir=tmp_path
    )


def test_reminder_flow(tmp_path):
    assert say("알림 목록", tmp_path) == "예약된 알림이 없어요."
    assert say("10분 뒤에 회의 알려줘", tmp_path) == (
        "알겠어요! 오늘 오전 10시 10분에 '회의' 알려드릴게요."
    )
    assert say("내일 9시에 병원 가기 알려줘", tmp_path) == (
        "알겠어요! 내일 오전 9시에 '병원 가기' 알려드릴게요."
    )
    assert "'알림'" in say("30초 뒤에 알려줘", tmp_path)
    listing = say("리마인더 목록", tmp_path)
    assert "3개" in listing
    assert listing.index("오전 10시 10분") < listing.index("내일 오전 9시")

    due = reminders.pop_due(tmp_path, NOW + timedelta(minutes=10))
    assert [r.text for r in due] == ["알림", "회의"]
    assert "1개" in say("알림 목록", tmp_path)


def test_reminder_with_explicit_keyword_and_time_in_middle(tmp_path):
    answer = say("회의 내일 9시에 리마인드 해줘", tmp_path)
    assert answer == "알겠어요! 내일 오전 9시에 '회의' 알려드릴게요."


@pytest.mark.parametrize(
    "text",
    [
        "25시에 회의 알려줘",
        "25시 회의 리마인드 해줘",
        "12월 32일 9시에 파티 리마인드 해줘",
        "32일 9시에 파티 리마인드 해줘",  # 못 읽은 날짜 뒤의 시각만 쓰지 않는다
    ],
)
def test_reminder_unparseable_time_stays_local(tmp_path, text):
    assert "이해하지 못했어요" in say(text, tmp_path)
    assert reminders.list_pending(tmp_path, NOW) == []


def test_reminder_in_the_past(tmp_path):
    assert "이미 지났어요" in say("오늘 9시에 회의 알려줘", tmp_path, NOW.replace(hour=22))


def test_reminder_storage_error_is_friendly(tmp_path):
    (tmp_path / "reminders.json").write_text("{", encoding="utf-8")
    assert "손상" in say("10분 뒤에 회의 알려줘", tmp_path)


def test_convert(tmp_path):
    assert say("10km는 몇 마일", tmp_path) == "10킬로미터는 약 6.2137마일이에요."
    assert say("5 lb to kg", tmp_path) == "5파운드는 약 2.268킬로그램이에요."
    assert "같은 종류" in say("10km는 몇 kg", tmp_path)


class TestDday:
    def test_future(self, tmp_path):
        assert (
            say("12월 25일까지 며칠", tmp_path) == "2026년 12월 25일(금)까지 50일 남았어요. (D-50)"
        )
        assert say("D-day 2026-12-25", tmp_path) == "2026년 12월 25일(금)까지 50일 남았어요. (D-50)"

    def test_month_day_already_passed_means_next_year(self, tmp_path):
        assert "2027년 3월 1일" in say("3월 1일까지 며칠", tmp_path)

    def test_today_and_past(self, tmp_path):
        assert "오늘" in say("D-day 2026-11-05", tmp_path)
        assert say("D-day 2026-11-01", tmp_path) == "2026년 11월 1일(일)은 4일 지났어요. (D+4)"

    def test_invalid_date(self, tmp_path):
        assert "이해하지 못했어요" in say("D-day 2026-02-30", tmp_path)


class TestHolidays:
    """공휴일 데이터는 holidays 모듈의 몫이라, 여기서는 가짜 데이터로 형식만 본다."""

    @pytest.fixture
    def fake(self, monkeypatch):
        holidays = pytest.importorskip("jev.skills.holidays")
        data = {
            date(2026, 11, 5): "가짜휴일",
            date(2026, 12, 25): "성탄절",
            date(2026, 11, 20): "설날 연휴",
        }

        def check(year):
            if year not in range(2025, 2028):
                raise holidays.UnsupportedYearError(year)

        def holidays_in_year(year):
            check(year)
            return sorted((d, n) for d, n in data.items() if d.year == year)

        def holiday_name(d):
            check(d.year)
            return data.get(d)

        def next_holiday(on_or_after):
            later = [(d, n) for d, n in sorted(data.items()) if d >= on_or_after]
            return later[0] if later else None

        monkeypatch.setattr(holidays, "SUPPORTED_YEARS", range(2025, 2028))
        monkeypatch.setattr(holidays, "holidays_in_year", holidays_in_year)
        monkeypatch.setattr(holidays, "holiday_name", holiday_name)
        monkeypatch.setattr(holidays, "next_holiday", next_holiday)
        return holidays

    def test_next(self, fake, tmp_path):
        tomorrow = NOW + timedelta(days=1)
        assert say("다음 공휴일 언제야?", tmp_path, tomorrow) == (
            "다음 공휴일은 2026년 11월 20일(금) 설날 연휴예요. 14일 남았어요."
        )
        assert say("다음 공휴일", tmp_path) == "오늘(2026년 11월 5일(목))이 바로 가짜휴일이에요!"

    def test_next_none(self, fake, tmp_path):
        later = datetime(2027, 1, 1, tzinfo=local_skills.TIMEZONE)
        assert "2027년까지의 공휴일만" in say("다음 공휴일", tmp_path, later)

    def test_year(self, fake, tmp_path):
        answer = say("올해 공휴일", tmp_path)
        assert answer.splitlines() == [
            "2026년 공휴일은 3일이에요:",
            "- 11월 5일(목) 가짜휴일",
            "- 11월 20일(금) 설날 연휴",
            "- 12월 25일(금) 성탄절",
        ]
        assert say("2027년 공휴일", tmp_path).startswith("2027년 공휴일은 0일")

    def test_unsupported_year(self, fake, tmp_path):
        assert say("2030년 공휴일", tmp_path) == (
            "2030년 공휴일 정보는 아직 없어요. 2025~2027년만 알려드릴 수 있어요."
        )

    def test_check(self, fake, tmp_path):
        assert (
            say("오늘 공휴일이야?", tmp_path) == "네, 오늘은 가짜휴일이에요. (2026년 11월 5일(목))"
        )
        assert say("내일 공휴일이야?", tmp_path) == (
            "아니요, 내일은 공휴일이 아니에요. (2026년 11월 6일(금))"
        )
        assert say("모레 쉬는 날이야?", tmp_path) == (
            "모레는 공휴일은 아니지만 주말이에요. (2026년 11월 7일(토))"
        )

    def test_check_unsupported_year(self, fake, tmp_path):
        later = datetime(2031, 1, 1, tzinfo=local_skills.TIMEZONE)
        assert "2031년" in say("오늘 공휴일이야?", tmp_path, later)


def test_real_holiday_data_smoke(tmp_path):
    pytest.importorskip("jev.skills.holidays")
    answer = say("다음 공휴일", tmp_path)
    assert answer.startswith("다음 공휴일은 2026년 12월 25일(금)")


def test_reminder_with_calendar_date(tmp_path):
    assert say("12월 25일 9시에 파티 리마인드 해줘", tmp_path) == (
        "알겠어요! 12월 25일(금) 오전 9시에 '파티' 알려드릴게요."
    )
    assert say("다음 달 3일 오후 2시에 치과 알려줘", tmp_path) == (
        "알겠어요! 12월 3일(목) 오후 2시에 '치과' 알려드릴게요."
    )
    due = reminders.list_pending(tmp_path, NOW)
    assert [r.due.date() for r in due] == [date(2026, 12, 3), date(2026, 12, 25)]


def test_naive_current_is_treated_as_seoul(tmp_path):
    naive = datetime(2026, 11, 5, 10, 0)
    assert local_skills.run("time", naive) == "지금은 10시 00분이에요."
    answer = local_skills.run("remind_add", naive, text="10분 뒤에 회의 알려줘", data_dir=tmp_path)
    assert answer == "알겠어요! 오늘 오전 10시 10분에 '회의' 알려드릴게요."
    assert local_skills.run("memo_add", naive, text="메모: 우유", data_dir=tmp_path).endswith(
        "우유"
    )
    from jev.skills import memo

    assert memo.list_memos(tmp_path)[0].created_at == "2026-11-05T10:00:00+09:00"


def test_memo_ids_not_reused_after_deleting_newest(tmp_path):
    say("메모: a", tmp_path)
    say("메모: b", tmp_path)
    assert say("메모 삭제 2", tmp_path) == "#2 메모를 지웠어요: b"
    assert say("메모: c", tmp_path) == "메모했어요 (#3): c"


def test_memo_keeps_word_ending_in_i(tmp_path):
    assert say("고양이라고 메모해줘", tmp_path) == "메모했어요 (#1): 고양이"


def test_convert_huge_number(tmp_path):
    assert say("1" + "0" * 400 + "km는 몇 마일", tmp_path) == "숫자가 너무 커서 계산할 수 없어요."
