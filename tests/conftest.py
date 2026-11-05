import os

import pytest

JEV_VARS = [
    "JEV_MODEL",
    "JEV_MEMORY",
    "JEV_MAX_HISTORY_MESSAGES",
    "JEV_MAX_HISTORY_BYTES",
    "JEV_MAX_TOKENS",
    "JEV_STREAM",
    "JEV_ENV_FILE",
]


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """테스트가 실제 ~/.jev 나 사용자의 환경변수를 건드리지 않게 한다.

    .env 로딩은 os.environ을 직접 바꾸므로 테스트가 끝나면 통째로 되돌린다.
    """
    saved = dict(os.environ)
    for name in JEV_VARS:
        os.environ.pop(name, None)
    os.environ["JEV_HOME"] = str(tmp_path / "jev-home")
    yield
    os.environ.clear()
    os.environ.update(saved)
