import pytest

from jev.router import route


@pytest.mark.parametrize(
    "text, skill",
    [
        ("몇 시야?", "time"),
        ("지금 몇시", "time"),
        ("시간?", "time"),
        ("오늘 날짜", "date"),
        ("오늘 무슨 요일이야?", "date"),
        ("며칠이야", "date"),
        ("/help", "help"),
        ("도움말", "help"),
        ("/reset", "reset"),
        ("초기화", "reset"),
    ],
)
def test_local_requests(text, skill):
    r = route(text)
    assert r.target == "local"
    assert r.skill == skill


@pytest.mark.parametrize(
    "text",
    [
        "회의 몇 시야?",
        "크리스마스는 무슨 요일이야?",
        "서울에서 부산까지 몇 시간 걸려?",
    ],
)
def test_contextual_questions_go_to_claude(text):
    assert route(text).target == "claude"


def test_short_chat_is_low_effort():
    r = route("안녕 Jev!")
    assert (r.target, r.effort) == ("claude", "low")


def test_keyword_request_is_high_effort():
    r = route("이 코드 왜 에러 나는지 봐줘")
    assert (r.target, r.effort) == ("claude", "high")


def test_long_request_is_high_effort():
    assert route("가" * 300).effort == "high"


def test_medium_request():
    r = route("이번 주말에 가볍게 다녀올 만한 서울 근교 여행지 몇 곳 추천해 줄래?")
    assert (r.target, r.effort) == ("claude", "medium")


def test_route_is_backward_compatible():
    r = route("몇 시야?")
    assert r.args == ""
    assert route("안녕").args == ""


@pytest.mark.parametrize(
    "text, skill, args",
    [
        # 메모
        ("메모: 우유 사기", "memo_add", "우유 사기"),
        ("메모 : 우유 사기", "memo_add", "우유 사기"),
        ("메모해줘 우유 사기", "memo_add", "우유 사기"),
        ("메모해줘: 우유 사기", "memo_add", "우유 사기"),
        ("메모 추가 우유 사기", "memo_add", "우유 사기"),
        ("우유 사기 메모해줘", "memo_add", "우유 사기"),
        ("우유 사기라고 메모해 줘", "memo_add", "우유 사기"),
        ("메모해줘", "memo_add", ""),
        ("메모 목록", "memo_list", ""),
        ("메모 보여줘", "memo_list", ""),
        ("내 메모 목록 보여줘", "memo_list", ""),
        ("메모 검색 우유", "memo_search", "우유"),
        ("메모 찾기: 우유 사기", "memo_search", "우유 사기"),
        ("메모에서 우유 찾아줘", "memo_search", "우유"),
        ("메모 삭제 3", "memo_delete", "3"),
        ("메모 삭제 3번", "memo_delete", "3"),
        ("3번 메모 지워줘", "memo_delete", "3"),
        # 리마인더
        ("10분 뒤에 회의 알려줘", "remind_add", "10분 뒤에 회의"),
        ("10분 뒤 회의 알려줘", "remind_add", "10분 뒤 회의"),
        ("내일 9시에 병원 가기 알려줘", "remind_add", "내일 9시에 병원 가기"),
        (
            "모레 오후 3시에 엄마한테 전화하라고 알려줘",
            "remind_add",
            "모레 오후 3시에 엄마한테 전화하라고",
        ),
        ("30초 뒤에 알려줘", "remind_add", "30초 뒤에"),
        ("25시에 회의 알려줘", "remind_add", "25시에 회의"),  # 시간 해석 실패도 로컬에서 안내
        ("회의 리마인드 해줘", "remind_add", "회의"),
        ("내일 9시 회의 알림 맞춰줘", "remind_add", "내일 9시 회의"),
        ("리마인더: 내일 9시 회의", "remind_add", "내일 9시 회의"),
        ("알림 추가 10분 뒤 라면", "remind_add", "10분 뒤 라면"),
        ("리마인더 목록", "remind_list", ""),
        ("알림 목록", "remind_list", ""),
        ("알림 보여줘", "remind_list", ""),
        # 단위 변환
        ("10km는 몇 마일", "convert", "10km는 몇 마일"),
        ("100 화씨를 섭씨로", "convert", "100 화씨를 섭씨로"),
        ("30평은 몇 제곱미터", "convert", "30평은 몇 제곱미터"),
        ("5 lb to kg", "convert", "5 lb to kg"),
        ("3인치 몇 cm", "convert", "3인치 몇 cm"),
        ("10km는 몇 kg", "convert", "10km는 몇 kg"),  # 차원이 달라도 로컬에서 안내
        # 공휴일 / D-day
        ("다음 공휴일", "holiday_next", ""),
        ("다음 공휴일 언제야?", "holiday_next", ""),
        ("다음 공휴일은 언제예요", "holiday_next", ""),
        ("올해 공휴일", "holiday_year", "올해"),
        ("2027년 공휴일", "holiday_year", "2027년"),
        ("내년 공휴일 알려줘", "holiday_year", "내년"),
        ("오늘 공휴일이야?", "holiday_check", "오늘"),
        ("내일 쉬는 날이야?", "holiday_check", "내일"),
        ("12월 25일까지 며칠", "dday", "12월 25일"),
        ("2027년 1월 1일까지 며칠 남았어?", "dday", "2027년 1월 1일"),
        ("D-day 2026-12-25", "dday", "2026-12-25"),
        ("디데이 2026.12.25", "dday", "2026.12.25"),
    ],
)
def test_new_local_skills(text, skill, args):
    r = route(text)
    assert (r.target, r.skill, r.args) == ("local", skill, args)


@pytest.mark.parametrize(
    "text",
    [
        "메모 앱 추천해줘",
        "메모하는 습관 들이는 법",
        "메모장에서 글자 크기 바꾸는 법",
        "단위 변환 원리 설명해줘",
        "마일이 몇 km인지 왜 그런지 설명해줘",
        "내일 날씨 알려줘",
        "9시 뉴스 알려줘",
        "오늘 9시에 뭐 있는지 알려줘",
        "알림이 안 와요",
        "공휴일 제도에 대해 알려줘",
        "크리스마스까지 며칠 남았어?",
        "다음 공휴일에 어디 갈까?",
        "리마인더 앱 뭐가 좋아?",
    ],
)
def test_near_misses_go_to_claude(text):
    assert route(text).target == "claude"
