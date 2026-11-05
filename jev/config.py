"""환경변수와 선택적 `.env` 파일에서 Jev 설정을 읽는다.

우선순위: 이미 설정된 환경변수 > `.env` 파일 > 기본값.
`.env`는 이미 있는 환경변수를 덮어쓰지 않는다.

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `JEV_MODEL` | (없음) | Claude 모델 ID. Claude를 호출할 때만 필요 |
| `JEV_HOME` | `~/.jev` | 대화 기록, 메모, 알림을 저장할 폴더 |
| `JEV_MEMORY` | `on` | 대화 기록을 파일에 저장할지 (`on`/`off`) |
| `JEV_MAX_HISTORY_MESSAGES` | `40` | 저장·전송할 대화 메시지 최대 개수 |
| `JEV_MAX_HISTORY_BYTES` | `200000` | 대화 기록 JSON 최대 크기(바이트) |
| `JEV_MAX_TOKENS` | `16000` | Claude 응답 최대 토큰 |
| `JEV_STREAM` | `on` | CLI에서 답변을 스트리밍으로 출력할지 |
| `JEV_ENV_FILE` | `./.env` | 읽을 `.env` 파일 경로 |
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path

MODEL_ENV = "JEV_MODEL"
HOME_ENV = "JEV_HOME"
MEMORY_ENV = "JEV_MEMORY"
MAX_MESSAGES_ENV = "JEV_MAX_HISTORY_MESSAGES"
MAX_BYTES_ENV = "JEV_MAX_HISTORY_BYTES"
MAX_TOKENS_ENV = "JEV_MAX_TOKENS"
STREAM_ENV = "JEV_STREAM"
ENV_FILE_ENV = "JEV_ENV_FILE"

DEFAULT_MAX_MESSAGES = 40
DEFAULT_MAX_BYTES = 200_000
DEFAULT_MAX_TOKENS = 16_000

_TRUE = {"1", "true", "yes", "on", "y", "예", "켜기"}
_FALSE = {"0", "false", "no", "off", "n", "아니오", "끄기"}
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def default_data_dir() -> Path:
    """JEV_HOME이 없을 때 쓰는 데이터 폴더 (~/.jev)."""
    return Path.home() / ".jev"


class ConfigError(ValueError):
    """설정값이 잘못되었을 때. 메시지는 사용자에게 그대로 보여 준다."""


@dataclass(frozen=True)
class Config:
    model: str | None
    data_dir: Path
    memory_enabled: bool = True
    max_history_messages: int = DEFAULT_MAX_MESSAGES
    max_history_bytes: int = DEFAULT_MAX_BYTES
    max_tokens: int = DEFAULT_MAX_TOKENS
    stream: bool = True

    @property
    def history_path(self) -> Path:
        return self.data_dir / "history.json"

    def require_model(self) -> str:
        if not self.model:
            raise ConfigError(
                f"환경변수 {MODEL_ENV} 에 사용할 Claude 모델 ID를 지정하세요. "
                f"(예: export {MODEL_ENV}=<모델 ID> 또는 .env 파일에 {MODEL_ENV}=<모델 ID>)"
            )
        return self.model

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        """환경변수(기본: os.environ)에서 설정을 만든다. `.env`는 읽지 않는다."""
        env = os.environ if env is None else env
        home = env.get(HOME_ENV, "").strip()
        data_dir = Path(home).expanduser() if home else default_data_dir()
        return cls(
            model=env.get(MODEL_ENV, "").strip() or None,
            data_dir=data_dir,
            memory_enabled=_parse_bool(env, MEMORY_ENV, default=True),
            max_history_messages=_parse_int(env, MAX_MESSAGES_ENV, DEFAULT_MAX_MESSAGES, 2),
            max_history_bytes=_parse_int(env, MAX_BYTES_ENV, DEFAULT_MAX_BYTES, 1_000),
            max_tokens=_parse_int(env, MAX_TOKENS_ENV, DEFAULT_MAX_TOKENS, 1),
            stream=_parse_bool(env, STREAM_ENV, default=True),
        )


def load(env_file: str | Path | None = None) -> Config:
    """`.env`를 os.environ에 반영한 뒤 설정을 읽는다.

    env_file을 주지 않으면 JEV_ENV_FILE, 그것도 없으면 현재 폴더의 `.env`를 쓴다.
    명시적으로 지정한 파일이 없으면 ConfigError, 기본 `.env`가 없으면 그냥 넘어간다.
    """
    explicit = env_file is not None or bool(os.environ.get(ENV_FILE_ENV))
    path = Path(env_file or os.environ.get(ENV_FILE_ENV) or ".env").expanduser()
    if path.is_file():
        load_dotenv(path)
    elif explicit:
        raise ConfigError(f".env 파일을 찾을 수 없어요: {path}")
    return Config.from_env()


def parse_dotenv(text: str, source: str = ".env") -> dict[str, str]:
    """간단한 `.env` 문법을 해석한다.

    지원: `KEY=VALUE`, `export KEY=VALUE`, 빈 줄, `#` 주석, 작은/큰따옴표 값,
    따옴표 없는 값 뒤의 ` # 주석`. 큰따옴표 안의 `\\n`은 줄바꿈으로 바꾼다.
    """
    result: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if re.match(r"export\s", line):
            line = line[len("export") :].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not _KEY.match(key):
            raise ConfigError(
                f"{source} {lineno}번째 줄을 해석할 수 없어요: KEY=VALUE 형식이어야 해요."
            )
        value = value.strip()
        if value[:1] in {'"', "'"}:
            value = _parse_quoted(value, source, lineno)
        elif value.startswith("#"):
            value = ""  # KEY=  # 주석
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        result[key] = value
    return result


def _parse_quoted(value: str, source: str, lineno: int) -> str:
    """따옴표 값을 해석한다. 큰따옴표 안에서는 \\" \\\\ \\n 이스케이프를 지원한다."""
    quote = value[0]
    chars: list[str] = []
    i = 1
    while i < len(value):
        ch = value[i]
        if quote == '"' and ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            chars.append({"n": "\n", '"': '"', "\\": "\\"}.get(nxt, "\\" + nxt))
            i += 2
            continue
        if ch == quote:
            rest = value[i + 1 :].strip()
            if rest and not rest.startswith("#"):
                raise ConfigError(
                    f"{source} {lineno}번째 줄: 닫는 따옴표 뒤에 다른 글자가 있어요 ({rest!r})."
                )
            return "".join(chars)
        chars.append(ch)
        i += 1
    raise ConfigError(f"{source} {lineno}번째 줄: 따옴표({quote})가 닫히지 않았어요.")


def load_dotenv(path: Path, environ: MutableMapping[str, str] | None = None) -> dict[str, str]:
    """`.env` 파일 값을 environ(기본 os.environ)에 넣는다. 이미 있는 키는 건드리지 않는다."""
    environ = os.environ if environ is None else environ
    try:
        text = path.read_text(encoding="utf-8-sig")  # BOM이 있어도 읽는다
    except OSError as e:
        raise ConfigError(f".env 파일을 읽을 수 없어요: {path} ({e.strerror})") from e
    except UnicodeDecodeError as e:
        raise ConfigError(f".env 파일은 UTF-8이어야 해요: {path}") from e
    values = parse_dotenv(text, source=str(path))
    for key, value in values.items():
        environ.setdefault(key, value)
    return values


def _parse_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    raise ConfigError(
        f"환경변수 {name} 값 '{raw}'을(를) 이해할 수 없어요. on 또는 off로 지정하세요."
    )


def _parse_int(env: Mapping[str, str], name: str, default: int, minimum: int) -> int:
    raw = env.get(name, "").strip().replace("_", "")
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"환경변수 {name} 는 정수여야 해요. (현재 값: '{raw}')") from None
    if value < minimum:
        raise ConfigError(f"환경변수 {name} 는 {minimum} 이상이어야 해요. (현재 값: {value})")
    return value
