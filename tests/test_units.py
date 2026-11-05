import pytest

from jev.skills import units
from jev.skills.units import ConversionError, convert, format_number, parse_request


@pytest.mark.parametrize(
    "value, src, dst, expected",
    [
        (10, "km", "mi", 6.21371192),
        (1, "mi", "m", 1609.344),
        (3, "in", "cm", 7.62),
        (1, "ft", "in", 12),
        (1000, "mm", "m", 1),
        (5, "lb", "kg", 2.26796185),
        (16, "oz", "lb", 1),
        (1, "근", "g", 600),
        (100, "F", "C", 37.7777778),
        (0, "C", "F", 32),
        (0, "C", "K", 273.15),
        (-40, "F", "C", -40),
        (30, "평", "m2", 99.1735537),
        (1, "m2", "평", 0.3025),
        (1, "gal", "l", 3.785411784),
        (1500, "ml", "l", 1.5),
    ],
)
def test_convert(value, src, dst, expected):
    assert convert(value, src, dst) == pytest.approx(expected, rel=1e-6)


def test_cross_dimension_rejected():
    with pytest.raises(ConversionError, match="같은 종류"):
        convert(10, "km", "kg")


def test_below_absolute_zero_rejected():
    with pytest.raises(ConversionError, match="절대영도"):
        convert(-300, "C", "F")


@pytest.mark.parametrize(
    "x, expected",
    [
        (6.213711922, "6.2137"),
        (2.5, "2.5"),
        (32.0, "32"),
        (0.0, "0"),
        (-0.00001, "-0.00001"),
        (0.000123456, "0.0001235"),
        (16093.44, "16,093.44"),
        (-40.0, "-40"),
        (1e-9 - 1e-9, "0"),
    ],
)
def test_format_number(x, expected):
    assert format_number(x) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("10km는 몇 마일", (10, "km", "mi")),
        ("10km는 몇 마일이야?", (10, "km", "mi")),
        ("100 화씨를 섭씨로", (100, "F", "C")),
        ("100 화씨를 섭씨로 바꿔줘", (100, "F", "C")),
        ("30평은 몇 제곱미터", (30, "평", "m2")),
        ("5 lb to kg", (5, "lb", "kg")),
        ("5 lbs in kg", (5, "lb", "kg")),
        ("5lb -> kg", (5, "lb", "kg")),
        ("3인치 몇 cm", (3, "in", "cm")),
        ("섭씨 30도는 화씨 몇 도", (30, "C", "F")),
        ("1,500ml는 몇 리터", (1500, "ml", "l")),
        ("2.5 KM to Miles", (2.5, "km", "mi")),
        ("1 gal to L", (1, "gal", "l")),
        ("98.6℉를 ℃로", (98.6, "F", "C")),
    ],
)
def test_parse_request(text, expected):
    req = parse_request(text)
    assert req is not None
    assert (req.value, req.src, req.dst) == expected


@pytest.mark.parametrize(
    "text",
    [
        "단위 변환 원리 설명해줘",
        "마일이 뭐야?",
        "10km 달리기 팁 알려줘",
        "km를 마일로",  # 숫자가 없음
        "10 parsec to km",  # 모르는 단위
    ],
)
def test_parse_request_rejects(text):
    assert parse_request(text) is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("10km는 몇 마일", "10킬로미터는 약 6.2137마일이에요."),
        ("100 화씨를 섭씨로", "화씨 100도는 약 섭씨 37.7778도예요."),
        ("30평은 몇 제곱미터", "30평은 약 99.1736제곱미터예요."),
        ("0 C to F", "섭씨 0도는 화씨 32도예요."),
        ("1근은 몇 g", "1근은 600그램이에요."),
        ("3인치 몇 cm", "3인치는 7.62센티미터예요."),
        ("10km는 몇 kg", None),
    ],
)
def test_reply(text, expected):
    answer = units.reply(text)
    if expected is None:
        assert "바꿀 수는 없어요" in answer
    else:
        assert answer == expected


def test_reply_unparseable():
    assert "이해하지 못했어요" in units.reply("아무 말")


def test_non_finite_rejected():
    with pytest.raises(ConversionError, match="너무 커서"):
        convert(float("inf"), "km", "mi")
    with pytest.raises(ConversionError, match="너무 커서"):
        convert(1e308, "km", "mm")  # 결과가 inf
    assert units.reply("1" + "0" * 400 + "km는 몇 마일") == "숫자가 너무 커서 계산할 수 없어요."


def test_milli_means_milliliter():
    req = parse_request("500밀리는 몇 리터")
    assert req is not None
    assert (req.src, req.dst) == ("ml", "l")
