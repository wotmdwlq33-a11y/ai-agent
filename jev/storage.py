"""JSON 파일 저장 도우미. 대화 기록(memory)과 로컬 기능(메모·알림)이 함께 쓴다.

쓰기는 항상 임시 파일에 쓴 뒤 os.replace로 바꿔 끼워, 중간에 끊겨도 파일이 깨지지 않게 한다.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

__all__ = [
    "StorageError",
    "ensure_private_dir",
    "file_lock",
    "load_records",
    "save_records",
    "write_json_atomic",
]


class StorageError(RuntimeError):
    """저장 파일을 읽거나 쓸 수 없을 때. 메시지는 사용자에게 그대로 보여줘도 된다."""


def ensure_private_dir(path: Path) -> None:
    """폴더가 없으면 만든다. 새로 만드는 폴더는 본인만 볼 수 있게(700) 한다.

    대화 기록과 메모가 들어가므로 다른 사용자가 목록을 보지 못하게 한다.
    이미 있는 폴더의 권한은 바꾸지 않는다.
    """
    path.mkdir(mode=0o700, parents=True, exist_ok=True)


def load_records(path: Path) -> list[dict[str, Any]]:
    """JSON 배열(객체 목록) 파일을 읽는다.

    파일이 없거나 비어 있으면 빈 목록을 돌려준다. 내용이 깨졌으면 사용자의 데이터를
    덮어쓰지 않도록 파일은 그대로 두고 StorageError를 낸다.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError) as e:
        raise StorageError(f"저장 파일({path})을 읽을 수 없어요: {e}") from e
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise StorageError(
            f"저장 파일({path})이 손상돼서 읽을 수 없어요 ({e.lineno}행 JSON 오류). "
            "파일을 고치거나 다른 곳으로 옮긴 뒤 다시 시도해 주세요."
        ) from e
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise StorageError(
            f"저장 파일({path})의 형식이 올바르지 않아요. "
            "파일을 고치거나 다른 곳으로 옮긴 뒤 다시 시도해 주세요."
        )
    return data


def save_records(path: Path, records: list[dict[str, Any]]) -> None:
    """객체 목록을 JSON 배열로 저장한다."""
    write_json_atomic(path, records)


def write_json_atomic(path: Path, data: Any, indent: int = 2) -> None:
    """data를 JSON으로 path에 원자적으로 쓴다. 실패하면 StorageError."""
    try:
        ensure_private_dir(path.parent)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    except OSError as e:
        raise StorageError(f"저장 파일({path})을 쓸 수 없어요: {e}") from e
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException as e:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        if isinstance(e, OSError):
            raise StorageError(f"저장 파일({path})을 쓸 수 없어요: {e}") from e
        raise


@contextlib.contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """path를 읽고-고치고-쓰는 동안 다른 프로세스가 같은 파일을 고치지 못하게 잠근다.

    `<파일 이름>.lock` 파일에 배타적 잠금(fcntl.flock)을 건다. 예를 들어 REPL의 알림 스레드와
    따로 실행한 `jev 메모: …`가 동시에 파일을 고쳐 한쪽 변경이 사라지는 것을 막는다.
    fcntl이 없는 환경(Windows)에서는 잠그지 않는다.
    """
    lock_path = path.with_name(path.name + ".lock")
    try:
        ensure_private_dir(lock_path.parent)
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        handle = os.fdopen(fd, "r+b")
    except OSError as e:
        raise StorageError(f"잠금 파일({lock_path})을 만들 수 없어요: {e}") from e
    try:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if fcntl is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
