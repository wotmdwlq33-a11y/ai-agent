from pathlib import Path

import pytest

from jev import config
from jev.config import Config, ConfigError, load_dotenv, parse_dotenv


def test_defaults(monkeypatch):
    monkeypatch.delenv("JEV_HOME")
    cfg = Config.from_env({})
    assert cfg.model is None
    assert cfg.data_dir == Path.home() / ".jev"
    assert cfg.memory_enabled is True
    assert cfg.stream is True
    assert cfg.max_history_messages == config.DEFAULT_MAX_MESSAGES
    assert cfg.history_path == cfg.data_dir / "history.json"


def test_values_from_env(tmp_path):
    cfg = Config.from_env(
        {
            "JEV_MODEL": " some-model ",
            "JEV_HOME": str(tmp_path),
            "JEV_MEMORY": "off",
            "JEV_STREAM": "no",
            "JEV_MAX_HISTORY_MESSAGES": "10",
            "JEV_MAX_HISTORY_BYTES": "50_000",
            "JEV_MAX_TOKENS": "2048",
        }
    )
    assert cfg.model == "some-model"
    assert cfg.data_dir == tmp_path
    assert (cfg.memory_enabled, cfg.stream) == (False, False)
    assert (cfg.max_history_messages, cfg.max_history_bytes, cfg.max_tokens) == (10, 50_000, 2048)


def test_home_expands_tilde():
    cfg = Config.from_env({"JEV_HOME": "~/somewhere"})
    assert cfg.data_dir == Path.home() / "somewhere"


@pytest.mark.parametrize(
    "env, fragment",
    [
        ({"JEV_MEMORY": "maybe"}, "JEV_MEMORY"),
        ({"JEV_MAX_TOKENS": "many"}, "정수"),
        ({"JEV_MAX_HISTORY_MESSAGES": "1"}, "2 이상"),
    ],
)
def test_invalid_values_have_clear_messages(env, fragment):
    with pytest.raises(ConfigError, match=fragment):
        Config.from_env(env)


def test_require_model():
    assert Config.from_env({"JEV_MODEL": "m"}).require_model() == "m"
    with pytest.raises(ConfigError, match="JEV_MODEL"):
        Config.from_env({}).require_model()


def test_parse_dotenv():
    text = """
# 주석
export JEV_MODEL=abc
JEV_HOME = "~/my jev"
QUOTED='a # not comment'
INLINE=value # comment
NEWLINE="a\\nb"
EMPTY=
"""
    assert parse_dotenv(text) == {
        "JEV_MODEL": "abc",
        "JEV_HOME": "~/my jev",
        "QUOTED": "a # not comment",
        "INLINE": "value",
        "NEWLINE": "a\nb",
        "EMPTY": "",
    }


@pytest.mark.parametrize("line, fragment", [("NOEQUALS", "1번째 줄"), ('A="open', "따옴표")])
def test_parse_dotenv_errors(line, fragment):
    with pytest.raises(ConfigError, match=fragment):
        parse_dotenv(line)


def test_load_dotenv_does_not_override(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=from-file\nB=from-file\n", encoding="utf-8")
    environ = {"A": "from-env"}
    load_dotenv(path, environ)
    assert environ == {"A": "from-env", "B": "from-file"}


def test_load_reads_explicit_env_file(tmp_path, monkeypatch):
    path = tmp_path / "custom.env"
    path.write_text("JEV_MODEL=from-dotenv\nJEV_STREAM=off\n", encoding="utf-8")
    cfg = config.load(path)
    assert cfg.model == "from-dotenv"
    assert cfg.stream is False


def test_load_missing_explicit_file_is_error(tmp_path):
    with pytest.raises(ConfigError, match="찾을 수 없어요"):
        config.load(tmp_path / "nope.env")


def test_load_without_default_dotenv_is_ok(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JEV_MODEL", "env-model")
    assert config.load().model == "env-model"


def test_env_file_variable(tmp_path, monkeypatch):
    path = tmp_path / "x.env"
    path.write_text("JEV_MODEL=via-var\n", encoding="utf-8")
    monkeypatch.setenv("JEV_ENV_FILE", str(path))
    assert config.load().model == "via-var"


@pytest.mark.parametrize(
    "line, expected",
    [
        ("JEV_MODEL=   # 나중에", ""),
        ('A="a\\"b"', 'a"b'),
        ('A="a\\\\b"', "a\\b"),
        ("A='x' # 주석", "x"),
        ("export\tA=1", "1"),
        ("A=b=c", "b=c"),
    ],
)
def test_parse_dotenv_edge_cases(line, expected):
    (value,) = parse_dotenv(line).values()
    assert value == expected


def test_text_after_closing_quote_is_error():
    with pytest.raises(ConfigError, match="닫는 따옴표 뒤"):
        parse_dotenv('A="x"y')


def test_dotenv_with_bom_and_crlf(tmp_path):
    path = tmp_path / ".env"
    path.write_bytes("﻿JEV_MODEL=bom\r\nJEV_STREAM=off\r\n".encode())
    environ: dict[str, str] = {}
    load_dotenv(path, environ)
    assert environ == {"JEV_MODEL": "bom", "JEV_STREAM": "off"}


def test_send_time_flag():
    assert Config.from_env({}).send_time is True
    assert Config.from_env({"JEV_SEND_TIME": "off"}).send_time is False


def test_hash_without_space_is_part_of_value():
    assert parse_dotenv("PASSWORD=#abc") == {"PASSWORD": "#abc"}
    assert parse_dotenv("A=   # 주석") == {"A": ""}
