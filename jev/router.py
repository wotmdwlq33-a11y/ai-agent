"""요청을 어디로 보낼지 결정한다.

- local: API 호출 없이 Jev가 바로 답할 수 있는 요청 (시간, 날짜, 도움말, 초기화)
- claude: 그 외 모든 요청. 요청 난이도에 따라 effort(low/medium/high)를 고른다.

규칙 기반이라 추가 API 호출이 없고, 결과는 항상 같다(테스트 가능).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

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


# 문장 전체가 일치할 때만 로컬 처리한다. "회의 몇 시야?"처럼
# 다른 맥락이 붙은 질문은 Claude로 보내야 하기 때문.
_END = r"\s*[?？.!]*\s*$"
LOCAL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("help", re.compile(r"^\s*(/help|도움말|help|뭐\s*할\s*수\s*있어)" + _END, re.I)),
    ("reset", re.compile(r"^\s*(/reset|초기화|대화\s*초기화)" + _END, re.I)),
    ("time", re.compile(r"^\s*(지금\s*|현재\s*)?(몇\s*시(야|예요|에요|니|지)?|시간|시각)" + _END)),
    ("date", re.compile(
        r"^\s*(오늘\s*)?(날짜|며칠(이야|이지|이에요)?|무슨\s*요일(이야|이지|이에요)?)" + _END
        + r"|^\s*오늘\s*(날짜|며칠|무슨\s*요일)")),
]

# 깊게 생각해야 하는 요청을 나타내는 단어
HIGH_KEYWORDS = re.compile(
    r"코드|구현|디버그|버그|에러|오류|설계|아키텍처|분석|비교|계획|전략|증명|리팩터|최적화|"
    r"알고리즘|논문|보고서|단계별|왜\s|원인|code|debug|design|analy[sz]e|plan|refactor",
    re.I,
)

SHORT_CHAT_MAX = 20
LONG_REQUEST_MIN = 300


def route(text: str) -> Route:
    for skill, pattern in LOCAL_PATTERNS:
        if pattern.search(text):
            return Route("local", skill=skill, reason=f"로컬 기능 '{skill}'과 일치")

    stripped = text.strip()
    if len(stripped) >= LONG_REQUEST_MIN or HIGH_KEYWORDS.search(stripped):
        return Route("claude", effort="high", reason="복잡한 요청 (긴 입력 또는 분석·코드 키워드)")
    if len(stripped) <= SHORT_CHAT_MAX:
        return Route("claude", effort="low", reason="짧은 일상 대화")
    return Route("claude", effort="medium", reason="일반 요청")
