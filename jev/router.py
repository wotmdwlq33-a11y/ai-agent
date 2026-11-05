"""요청을 어디로 보낼지 결정한다.

- local: API 호출 없이 Jev가 바로 답할 수 있는 요청
  (시간, 날짜, 도움말, 초기화, 메모, 리마인더, 단위 변환, 공휴일/D-day)
- claude: 그 외 모든 요청. 요청 난이도에 따라 effort(low/medium/high)를 고른다.

규칙 기반이라 추가 API 호출이 없고, 결과는 항상 같다(테스트 가능).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from jev.skills import timeparse, units

Target = Literal["local", "claude"]
Effort = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class Route:
    target: Target
    # target == "local"일 때 실행할 로컬 기능 이름
    skill: str | None = None
    # target == "claude"일 때 사용할 effort
    effort: Effort | None = None
    reason: str = ""
    # 로컬 기능에 넘길 내용 (예: 메모 본문, 검색어, 알림 문장). 없으면 "".
    args: str = ""


# 문장 전체가 일치할 때만 로컬 처리한다. "회의 몇 시야?"처럼
# 다른 맥락이 붙은 질문은 Claude로 보내야 하기 때문.
# 패턴에 (?P<args>...) 그룹이 있으면 그 내용이 Route.args가 된다.
_END = r"\s*[?？.!]*\s*$"
_PLEASE = r"(?:줘|주세요|줄래|줄래요|줘요)"
_MEMO_VERB = rf"(?:해\s*{_PLEASE}|해\s*둬|해\s*놔|좀\s*해\s*{_PLEASE}|추가|추가해\s*{_PLEASE})"
_SHOW = rf"(?:목록|리스트|전체|전부|보기|확인|보여\s*{_PLEASE}|뭐\s*있어|뭐\s*있지)"
_DELETE = rf"(?:삭제|지우기|지워\s*{_PLEASE}|삭제해\s*{_PLEASE})"
_DATE = (
    r"\d{4}\s*[-./]\s*\d{1,2}\s*[-./]\s*\d{1,2}"
    r"|(?:\d{4}\s*년\s*)?\d{1,2}\s*월\s*\d{1,2}\s*일"
)
_ASK = r"(?:이야|야|예요|이에요|인가요|이니|니|이지|지|일까|임)?"

LOCAL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("help", re.compile(r"^\s*(/help|도움말|help|뭐\s*할\s*수\s*있어)" + _END, re.I)),
    ("reset", re.compile(r"^\s*(/reset|초기화|대화\s*초기화)" + _END, re.I)),
    ("time", re.compile(r"^\s*(지금\s*|현재\s*)?(몇\s*시(야|예요|에요|니|지)?|시간|시각)" + _END)),
    (
        "date",
        re.compile(
            r"^\s*(오늘\s*)?(날짜|며칠|무슨\s*요일)\s*"
            rf"(이야|이지|이에요|예요|야|지|니|(좀\s*)?알려\s*{_PLEASE})?" + _END
        ),
    ),
    # 메모
    (
        "memo_list",
        re.compile(rf"^\s*(?:내\s*)?메모(?:들)?\s*{_SHOW}(?:\s*보여\s*{_PLEASE})?" + _END),
    ),
    (
        "memo_search",
        re.compile(
            r"^\s*메모\s*(?:검색|찾기|찾아\s*줘)\s*[:：]\s*(?P<args>\S.*?)\s*$"
            r"|^\s*메모\s*(?:검색|찾기|찾아\s*줘)\s+(?P<args2>\S.*?)\s*$"
            rf"|^\s*메모\s*에서\s*(?P<args3>\S.*?)\s*(?:을|를)?\s*(?:찾아|검색해)\s*{_PLEASE}"
            + _END
        ),
    ),
    (
        "memo_delete",
        re.compile(
            rf"^\s*메모\s*{_DELETE}\s*#?(?P<args>\d+)\s*번?(?:\s*{_DELETE})?"
            + _END
            + rf"|^\s*#?(?P<args2>\d+)\s*번\s*메모\s*(?:를|을)?\s*{_DELETE}"
            + _END
        ),
    ),
    (
        "memo_add",
        re.compile(
            rf"^\s*메모\s*{_MEMO_VERB}?\s*[:：]\s*(?P<args>.*?)\s*$"
            rf"|^\s*메모\s*{_MEMO_VERB}\s+(?P<args2>.+?)\s*$"
            rf"|^\s*(?P<args3>.+?)\s*메모\s*{_MEMO_VERB}"
            + _END
            + rf"|^\s*메모\s*{_MEMO_VERB}"
            + _END
        ),
    ),
    # 리마인더
    (
        "remind_list",
        re.compile(
            rf"^\s*(?:리마인더|알림|예약(?:된)?\s*알림)\s*{_SHOW}(?:\s*보여\s*{_PLEASE})?" + _END
        ),
    ),
    (
        "remind_add",
        re.compile(
            r"^\s*(?:리마인더|알림)\s*(?:추가|등록|설정)?\s*[:：]\s*(?P<args>.*?)\s*$"
            r"|^\s*(?:리마인더|알림)\s*(?:추가|등록|설정)\s+(?P<args2>.+?)\s*$"
        ),
    ),
    # 공휴일 / D-day
    (
        "holiday_next",
        re.compile(
            r"^\s*(?:다음|가장\s*가까운|이번)\s*(?:공휴일|휴일|빨간\s*날)\s*(?:은|이)?\s*"
            rf"(?:언제{_ASK}|며칠{_ASK}|뭐{_ASK}|알려\s*{_PLEASE})?" + _END
        ),
    ),
    (
        "holiday_year",
        re.compile(
            r"^\s*(?P<args>올해|내년|작년|\d{4}\s*년(?:도)?)\s*(?:의\s*)?공휴일\s*(?:은|이)?\s*"
            rf"(?:목록|리스트|전체|알려\s*{_PLEASE}|보여\s*{_PLEASE}|뭐\s*있어|언제{_ASK})?" + _END
        ),
    ),
    (
        "holiday_check",
        re.compile(
            r"^\s*(?P<args>오늘|내일|모레)\s*(?:은|는)?\s*(?:공휴일|휴일|쉬는\s*날|빨간\s*날)\s*"
            r"(?:이야|이에요|인가요|이니|야|이지|임|맞아|이야\s*아니야)?" + _END
        ),
    ),
    (
        "dday",
        re.compile(
            rf"^\s*(?P<args>{_DATE})\s*(?:까지|까진)\s*(?:며칠|몇\s*일)\s*"
            r"(?:남았어|남았지|남았나요|남았니|남음|남았어요|이야|야|예요|이에요|지)?"
            + _END
            + rf"|^\s*(?:d\s*-?\s*day|디데이)\s*[:：]?\s*(?P<args2>{_DATE})"
            + _END,
            re.I,
        ),
    ),
]

# 알림 문장: "<시간>에 <할 일> 알려줘". 시간 표현 + '에'로 시작해야 로컬 처리한다
# ("3일 뒤 날씨 알려줘"는 Claude로). "리마인드 해줘" / "알림 맞춰줘" / "리마인더:" /
# "알림 추가"처럼 알림을 분명히 말한 경우는 어딘가에 시간 표현이 있으면 로컬로 보낸다.
# 시간 값이 틀렸으면(25시) 로컬에서 "이해하지 못했어요"라고 답한다.
_REMIND_SENTENCE = re.compile(
    r"^\s*(?P<body>.*?)\s*(?:(?P<explicit>리마인드\s*해|알림\s*(?:해|설정해|맞춰|등록해))|알려)\s*"
    rf"{_PLEASE}" + _END
)
# "오늘 9시에 뭐 있는지 알려줘"처럼 질문이면 알림이 아니다.
_QUESTION_WORDS = re.compile(r"뭐|무엇|무슨|어떻게|어때|어떤|언제|몇|누구|어디|[는은인할을건]지\b")
# 메모/알림 명령처럼 생겼지만 사실은 질문·부탁인 문장 ("메모 추가 기능 어떻게 써?")
_QUESTIONISH = re.compile(
    r"[?？]\s*$|어떻게|어떡|뭐|무엇|무슨|왜|방법|추천|어디|언제|누구|누가|어때|어떤|설명|"
    r"기능|단축키|사용법|쓰는\s*법|하는\s*법|앱|어플|나요|까요|일까|인가"
)

# 깊게 생각해야 하는 요청을 나타내는 단어
HIGH_KEYWORDS = re.compile(
    r"코드|구현|디버그|버그|에러|오류|설계|아키텍처|분석|비교|계획|전략|증명|리팩터|최적화|"
    r"알고리즘|논문|보고서|단계별|왜\s|원인|code|debug|design|analy[sz]e|plan|refactor",
    re.I,
)

SHORT_CHAT_MAX = 20
LONG_REQUEST_MIN = 300


def _match_args(m: re.Match[str]) -> str:
    groups = m.groupdict()
    for name in ("args", "args2", "args3"):
        value = groups.get(name)
        if value:
            return value.strip()
    return ""


def _accept(skill: str, m: re.Match[str], text: str) -> bool:
    """패턴이 맞아도 로컬로 처리하면 안 되는 경우를 거른다."""
    loose = m.groupdict().get("args2") is not None or m.groupdict().get("args3") is not None
    if skill in ("memo_add", "memo_search") and loose and _QUESTIONISH.search(text):
        return False  # ':' 없는 느슨한 형태는 질문이면 Claude로
    if skill == "remind_add":
        if not timeparse.has_time_expression(_match_args(m)):
            return False  # "알림 설정 방법 알려줘" 등
        if loose and _QUESTIONISH.search(text):
            return False
    return True


def _route_args(skill: str, m: re.Match[str]) -> str:
    args = _match_args(m)
    if skill == "memo_add" and m.groupdict().get("args3"):
        # "우유 사기라고 메모해줘" → "우유 사기". '이라고'의 '이'는 남긴다
        # ("고양이라고"의 '이'는 낱말의 일부일 수 있어서).
        args = re.sub(r"\s*라고$", "", args).strip()
    return args


def _reminder_body(text: str) -> str | None:
    """알림 문장이면 시간+할 일 부분을, 아니면 None을 돌려준다."""
    m = _REMIND_SENTENCE.match(text)
    if not m:
        return None
    body = m.group("body").strip()
    if m.group("explicit"):
        if not timeparse.has_time_expression(body) or _QUESTIONISH.search(text):
            return None  # "카카오톡 알림 설정해줘", "아이폰 알림 맞춰줘"
        return body
    lead = timeparse.leading_time(body)
    if lead is None:
        return None
    end, _relative = lead
    rest = body[end:].lstrip()
    if not rest.startswith("에"):
        # "9시 뉴스 알려줘", "3일 뒤 날씨 알려줘"처럼 '에' 없이 붙은 말은 Claude로
        return None
    if _QUESTION_WORDS.search(rest):
        return None
    return body


def route(text: str) -> Route:
    for skill, pattern in LOCAL_PATTERNS:
        m = pattern.search(text)
        if m and _accept(skill, m, text):
            return Route(
                "local",
                skill=skill,
                reason=f"로컬 기능 '{skill}'과 일치",
                args=_route_args(skill, m),
            )

    body = _reminder_body(text)
    if body is not None:
        return Route("local", skill="remind_add", reason="로컬 기능 'remind_add'와 일치", args=body)

    if units.parse_request(text) is not None:
        return Route(
            "local", skill="convert", reason="로컬 기능 'convert'와 일치", args=text.strip()
        )

    stripped = text.strip()
    if len(stripped) >= LONG_REQUEST_MIN or HIGH_KEYWORDS.search(stripped):
        return Route("claude", effort="high", reason="복잡한 요청 (긴 입력 또는 분석·코드 키워드)")
    if len(stripped) <= SHORT_CHAT_MAX:
        return Route("claude", effort="low", reason="짧은 일상 대화")
    return Route("claude", effort="medium", reason="일반 요청")
