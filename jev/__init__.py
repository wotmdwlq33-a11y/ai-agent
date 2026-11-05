"""Jev: 개인 비서. 요청을 로컬 처리 또는 Claude로 라우팅한다."""

from importlib.metadata import PackageNotFoundError, version

from jev.assistant import Jev
from jev.router import Route, route

try:
    __version__ = version("jev")
except PackageNotFoundError:  # pragma: no cover - 설치하지 않고 소스에서 바로 실행할 때
    __version__ = "0+unknown"

__all__ = ["Jev", "Route", "__version__", "route"]
