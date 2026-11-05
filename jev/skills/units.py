"""단위 변환 (길이, 무게, 온도, 넓이, 부피). 규칙 기반, API 호출 없음.

예: "10km는 몇 마일", "100 화씨를 섭씨로", "30평은 몇 제곱미터", "5 lb to kg", "3인치 몇 cm"
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from jev.skills import josa


class ConversionError(ValueError):
    """변환할 수 없는 요청. 메시지는 그대로 보여줘도 된다."""


@dataclass(frozen=True)
class Unit:
    key: str
    dimension: str
    factor: float  # 기준 단위(m, g, m², ml)로 바꾸는 배수. 온도는 쓰지 않는다.
    name: str  # 한국어 표시 이름


DIMENSION_NAMES = {
    "length": "길이",
    "mass": "무게",
    "temperature": "온도",
    "area": "넓이",
    "volume": "부피",
}

UNITS: dict[str, Unit] = {
    u.key: u
    for u in [
        Unit("mm", "length", 0.001, "밀리미터"),
        Unit("cm", "length", 0.01, "센티미터"),
        Unit("m", "length", 1.0, "미터"),
        Unit("km", "length", 1000.0, "킬로미터"),
        Unit("in", "length", 0.0254, "인치"),
        Unit("ft", "length", 0.3048, "피트"),
        Unit("yd", "length", 0.9144, "야드"),
        Unit("mi", "length", 1609.344, "마일"),
        Unit("g", "mass", 1.0, "그램"),
        Unit("kg", "mass", 1000.0, "킬로그램"),
        Unit("lb", "mass", 453.59237, "파운드"),
        Unit("oz", "mass", 28.349523125, "온스"),
        # 근은 물건마다 다르다(고기 600g, 채소·과일 375g 등). 여기서는 고기 기준 600g.
        Unit("근", "mass", 600.0, "근"),
        Unit("C", "temperature", 1.0, "섭씨"),
        Unit("F", "temperature", 1.0, "화씨"),
        Unit("K", "temperature", 1.0, "켈빈"),
        Unit("m2", "area", 1.0, "제곱미터"),
        Unit("평", "area", 400 / 121, "평"),  # 1평 = 400/121 m² (약 3.3058 m²)
        Unit("ml", "volume", 1.0, "밀리리터"),
        Unit("l", "volume", 1000.0, "리터"),
        Unit("gal", "volume", 3785.411784, "갤런"),  # 미국 갤런
    ]
}

_ALIASES: dict[str, list[str]] = {
    "mm": ["mm", "밀리미터", "밀리"],
    "cm": ["cm", "센티미터", "센티", "센치"],
    "m": ["m", "meter", "meters", "미터"],
    "km": ["km", "kilometer", "kilometers", "킬로미터"],
    "in": ["in", "inch", "inches", "인치"],
    "ft": ["ft", "foot", "feet", "피트"],
    "yd": ["yd", "yard", "yards", "야드"],
    "mi": ["mi", "mile", "miles", "마일"],
    "g": ["g", "gram", "grams", "그램"],
    "kg": ["kg", "kilogram", "kilograms", "킬로그램"],
    "lb": ["lb", "lbs", "pound", "pounds", "파운드"],
    "oz": ["oz", "ounce", "ounces", "온스"],
    "근": ["근"],
    "C": ["C", "°C", "℃", "celsius", "섭씨"],
    "F": ["F", "°F", "℉", "fahrenheit", "화씨"],
    "K": ["K", "kelvin", "켈빈"],
    "m2": ["m2", "m²", "㎡", "sqm", "제곱미터", "평방미터"],
    "평": ["평"],
    "ml": ["ml", "mL", "cc", "밀리리터"],
    "l": ["l", "L", "liter", "liters", "litre", "litres", "리터"],
    "gal": ["gal", "gallon", "gallons", "갤런"],
}


def _build_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for key, aliases in _ALIASES.items():
        for alias in aliases:
            variants = {alias}
            # 여러 글자 영문 단위는 대소문자를 가리지 않는다 (KM, Kg, Miles ...).
            # 한 글자 단위(m, g, C, F, K, l)는 뜻이 갈릴 수 있어 적힌 그대로만 받는다.
            if alias.isascii() and len(alias) > 1:
                variants |= {alias.lower(), alias.upper(), alias.capitalize()}
            for v in variants:
                lookup.setdefault(v, key)
    return lookup


_LOOKUP = _build_lookup()
_UNIT = "|".join(re.escape(a) for a in sorted(_LOOKUP, key=len, reverse=True))
_NUM = r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|[-+]?\.\d+"
_SRC = rf"(?P<num>{_NUM})\s*(?P<src>{_UNIT})(?![A-Za-z])"
_DST = rf"(?P<dst>{_UNIT})(?![A-Za-z])"
_END = r"\s*[?？.!]*\s*$"

_REQUEST_PATTERNS = [
    # 10km는 몇 마일(이야)? / 3인치 몇 cm
    re.compile(
        rf"^\s*{_SRC}\s*(?:은|는|이|가|을|를)?\s*몇\s*{_DST}\s*"
        r"(?:이야|야|예요|이에요|인가요|일까|일까요|이지|지|이니|나와|돼)?" + _END
    ),
    # 100 화씨를 섭씨로 (바꿔줘) / 10km를 마일로 바꾸면?
    re.compile(
        rf"^\s*{_SRC}\s*(?:은|는|을|를)?\s*{_DST}\s*(?:으로|로)\s*"
        r"(?:(?:바꿔|변환해|환산해)\s*(?:줘|주세요|줄래|줄래요)?|바꾸면|변환하면|환산하면"
        r"|몇(?:이야)?)?" + _END
    ),
    # 5 lb to kg / 5 lb in kg / 5lb -> kg
    re.compile(rf"^\s*{_SRC}\s*(?:\s(?:to|in|TO|IN)\s|->|→|=)\s*{_DST}" + _END),
]

# "섭씨 30도" → "30 섭씨", "화씨 몇 도" → "몇 화씨"
_TEMP_VALUE = re.compile(rf"(섭씨|화씨)\s*({_NUM})\s*도")
_TEMP_QUESTION = re.compile(r"(섭씨|화씨)\s*몇\s*도")


@dataclass(frozen=True)
class ConversionRequest:
    value: float
    src: str  # UNITS 키
    dst: str


def parse_request(text: str) -> ConversionRequest | None:
    """문장 전체가 단위 변환 요청이면 ConversionRequest, 아니면 None."""
    normalized = _TEMP_QUESTION.sub(r"몇 \1", _TEMP_VALUE.sub(r"\2 \1", text))
    for pattern in _REQUEST_PATTERNS:
        m = pattern.match(normalized)
        if m:
            value = float(m.group("num").replace(",", ""))
            return ConversionRequest(value, _LOOKUP[m.group("src")], _LOOKUP[m.group("dst")])
    return None


def _to_kelvin(value: float, key: str) -> float:
    if key == "C":
        return value + 273.15
    if key == "F":
        return (value - 32) * 5 / 9 + 273.15
    return value


def _from_kelvin(kelvin: float, key: str) -> float:
    if key == "C":
        return kelvin - 273.15
    if key == "F":
        return (kelvin - 273.15) * 9 / 5 + 32
    return kelvin


def convert(value: float, src: str, dst: str) -> float:
    """value를 src 단위에서 dst 단위로 바꾼다 (UNITS 키). 차원이 다르면 ConversionError."""
    try:
        a, b = UNITS[src], UNITS[dst]
    except KeyError as e:
        raise ConversionError(f"모르는 단위예요: {e.args[0]}") from e
    if a.dimension != b.dimension:
        raise ConversionError(
            f"{DIMENSION_NAMES[a.dimension]}({a.name})를 "
            f"{DIMENSION_NAMES[b.dimension]}({b.name})로 바꿀 수는 없어요. "
            "같은 종류의 단위끼리만 변환할 수 있어요."
        )
    if a.dimension == "temperature":
        kelvin = _to_kelvin(value, src)
        if kelvin < -1e-9:
            raise ConversionError("절대영도(섭씨 -273.15도)보다 낮은 온도는 없어요.")
        return _from_kelvin(kelvin, dst)
    return value * a.factor / b.factor


def format_number(x: float) -> str:
    """소수점 아래 최대 4자리(1보다 작으면 유효숫자 4자리), 뒤쪽 0은 지운다."""
    if not math.isfinite(x):
        return str(x)
    ax = abs(x)
    if ax == 0 or ax >= 1:
        text = f"{x:,.4f}"
    else:
        digits = 3 - math.floor(math.log10(ax))
        text = f"{x:,.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _display(value: str, key: str) -> str:
    if key in ("C", "F"):
        return f"{UNITS[key].name} {value}도"
    return f"{value}{UNITS[key].name}"


def describe(request: ConversionRequest) -> str:
    """변환 결과를 한국어 문장으로. 변환할 수 없으면 ConversionError."""
    result = convert(request.value, request.src, request.dst)
    shown = format_number(result)
    # 부동소수점 오차(7.620000000000001 등)는 '약'을 붙이지 않는다
    exact = math.isclose(float(shown.replace(",", "")), result, rel_tol=1e-9, abs_tol=1e-12)
    approx = "" if exact else "약 "
    src_text = _display(format_number(request.value), request.src)
    dst_text = _display(shown, request.dst)
    return f"{josa(src_text, '은', '는')} {approx}{josa(dst_text, '이에요', '예요')}."


def reply(text: str) -> str:
    """사용자 문장을 받아 답을 만든다. 변환 요청이 아니거나 불가능하면 안내 문장."""
    request = parse_request(text)
    if request is None:
        return "어떤 단위를 바꿀지 이해하지 못했어요. '10km는 몇 마일'처럼 말해 주세요."
    try:
        return describe(request)
    except ConversionError as e:
        return str(e)
