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
