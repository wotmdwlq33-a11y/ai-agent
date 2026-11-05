"""터미널에서 Jev와 대화하는 REPL."""

from __future__ import annotations

import argparse
import dataclasses
import sys
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

import anthropic

from jev import __version__, korean
from jev import config as config_mod
from jev.assistant import Jev
from jev.config import ConfigError
from jev.memory import HistoryError
from jev.skills import reminders
from jev.skills.timeparse import format_korean_datetime
from jev.storage import StorageError

Output = Callable[[str], None]

PROMPT = "나: "
# 입력을 기다리는 동안 알림을 확인하는 간격(초)
REMINDER_POLL_SECONDS = 15.0
REMINDER_ERROR_PREFIX = "(알림을 확인하지 못했어요: "


def _print(text: str) -> None:
    print(text, flush=True)


def _write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """명령줄 옵션을 해석한다."""
    parser = argparse.ArgumentParser(prog="jev", description="Jev 개인 비서")
    parser.add_argument("--version", action="version", version=f"jev {__version__}")
    parser.add_argument("--debug", action="store_true", help="라우팅 결과도 함께 출력")
    parser.add_argument("--no-stream", action="store_true", help="답변을 한 번에 출력")
    parser.add_argument("--no-memory", action="store_true", help="대화 기록을 파일에 저장하지 않음")
    parser.add_argument("--env-file", type=Path, help="읽을 .env 파일 (기본: ./.env)")
    parser.add_argument(
        "message", nargs="*", help="주면 이 요청 하나만 처리하고 끝냄 (예: jev 메모 목록)"
    )
    # 옵션과 요청 단어가 섞여 있어도 된다 (예: jev 메모 --debug 목록)
    return parser.parse_intermixed_args(argv)


def _due_reminders(data_dir: Path) -> list[str]:
    """시간이 된 알림 문구를 꺼낸다. 알림 파일에 문제가 있어도 대화는 계속한다."""
    current = korean.now()
    try:
        due = reminders.pop_due(data_dir, current)
    except StorageError as e:
        return [f"{REMINDER_ERROR_PREFIX}{e})"]
    return [f"⏰ 알림: {r.text} ({format_korean_datetime(r.due, current)})" for r in due]


class ReminderWatcher(threading.Thread):
    """입력을 기다리는 동안에도 시간이 된 알림을 출력하는 백그라운드 스레드.

    lock은 REPL이 요청을 처리하는 동안 잡고 있는 잠금이다. 같은 잠금을 써서
    알림 파일을 동시에 고치거나, 스트리밍 답변 중간에 알림이 끼어드는 일을 막는다.
    """

    def __init__(
        self,
        data_dir: Path,
        lock: threading.Lock,
        emit: Output,
        interval: float = REMINDER_POLL_SECONDS,
    ) -> None:
        super().__init__(name="jev-reminders", daemon=True)
        self._data_dir = data_dir
        self._lock = lock
        self._emit = emit
        self._interval = interval
        self._stop_event = threading.Event()
        self._last_error: str | None = None

    def run(self) -> None:
        """stop()이 불릴 때까지 interval마다 알림을 확인한다."""
        while not self._stop_event.wait(self._interval):
            self.check_once()

    def check_once(self) -> None:
        """시간이 된 알림을 한 번 확인해 출력한다."""
        with self._lock:
            lines = _due_reminders(self._data_dir)
            errors = [line for line in lines if line.startswith(REMINDER_ERROR_PREFIX)]
            if errors:
                # 알림 파일 오류는 같은 내용을 15초마다 되풀이하지 않는다
                if errors[0] == self._last_error:
                    return
                self._last_error = errors[0]
            else:
                self._last_error = None
            if lines:
                # 입력 줄 위에 알림을 쓰고 프롬프트를 다시 보여 준다
                self._emit("\n" + "\n".join(lines) + "\n" + PROMPT)

    def stop(self) -> None:
        """스레드를 멈추도록 알린다."""
        self._stop_event.set()


def error_message(error: BaseException) -> str | None:
    """사용자에게 보여 줄 오류 문구. 예상하지 못한 오류면 None (그대로 올려 보낸다)."""
    if isinstance(error, ConfigError):
        return f"설정 오류 — {error}"
    if isinstance(error, anthropic.AuthenticationError):
        return "Claude 인증에 실패했어요. ANTHROPIC_API_KEY를 확인해 주세요."
    if isinstance(error, anthropic.RateLimitError):
        return "요청이 너무 많아요. 잠시 후 다시 시도해 주세요."
    if isinstance(error, anthropic.APIStatusError):
        if error.status_code < 400:
            # 스트리밍 도중 온 오류 이벤트는 HTTP 상태가 200이다. 오류 종류를 대신 보여 준다.
            return f"Claude API 오류가 났어요 ({_error_type(error.body) or '응답 중 오류'})."
        return f"Claude API 오류가 났어요 ({error.status_code})."
    if isinstance(error, anthropic.APIConnectionError):
        return "네트워크 연결을 확인해 주세요."
    if isinstance(error, StorageError):
        return str(error)
    return None


def _error_type(body: object) -> str | None:
    if isinstance(body, dict):
        error = body.get("error")
        kind = error.get("type") if isinstance(error, dict) else body.get("type")
        if isinstance(kind, str) and kind != "error":
            return kind
    return None


def respond(jev: Jev, text: str, *, stream: bool, debug: bool, out: Output, write: Output) -> int:
    """입력 한 줄을 처리하고 결과를 출력한다. 오류는 사용자에게 알리고 계속 진행한다.

    반환값은 one-shot 모드의 종료 코드다: 0 성공, 1 실행 오류, 2 설정 오류.
    """
    started = False

    def on_text(chunk: str) -> None:
        nonlocal started
        if not started:
            write("Jev: ")
            started = True
        write(chunk)

    try:
        answer = jev.handle(text, on_text=on_text if stream else None)
    except KeyboardInterrupt:
        # 답변 도중 Ctrl+C: 이번 답변만 멈추고 대화는 계속한다. 기록에는 남지 않는다.
        out(("\n" if started else "") + "Jev: (답변을 중단했어요)")
        return 130
    except Exception as e:
        message = error_message(e)
        if message is None:
            raise
        # 스트리밍 중이었다면 부분 답변 다음 줄에 오류를 쓴다
        out(("\n" if started else "") + f"Jev: {message}")
        return 2 if isinstance(e, ConfigError) else 1

    if debug:
        r = answer.route
        out(f"  [route] {r.target} skill={r.skill} effort={r.effort} ({r.reason})")
    if answer.streamed:
        write("\n")
        if answer.refused:
            out(f"Jev: (위 답변은 중단되었어요) {answer.text}")
    else:
        out(f"Jev: {answer.text}")
    if answer.warning:
        out(f"  (주의: {answer.warning})")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 진입점. 요청 단어가 있으면 한 번만 처리하고, 없으면 REPL을 연다. 종료 코드를 돌려준다."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        cfg = config_mod.load(args.env_file)
        if args.no_memory:
            cfg = dataclasses.replace(cfg, memory_enabled=False)
        jev = Jev(config=cfg)
    except (ConfigError, HistoryError) as e:
        print(f"Jev: 설정 오류 — {e}", file=sys.stderr)
        return 2

    stream = cfg.stream and not args.no_stream
    if args.message:
        for line in _due_reminders(cfg.data_dir):
            _print(line)
        text = " ".join(args.message).strip()
        if not text:
            print("Jev: 처리할 요청이 비어 있어요. 예: jev 메모 목록", file=sys.stderr)
            return 2
        return respond(jev, text, stream=stream, debug=args.debug, out=_print, write=_write)

    _print('Jev: 안녕하세요! 도움말은 "/help", 종료는 Ctrl+D 입니다.')
    lock = threading.Lock()
    watcher: ReminderWatcher | None = None
    if sys.stdin.isatty():
        watcher = ReminderWatcher(cfg.data_dir, lock, _write)
        watcher.start()
    try:
        while True:
            with lock:
                for line in _due_reminders(cfg.data_dir):
                    _print(line)
            try:
                text = input(PROMPT).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not text:
                continue
            with lock:
                respond(jev, text, stream=stream, debug=args.debug, out=_print, write=_write)
    finally:
        if watcher is not None:
            watcher.stop()
            # 알림을 파일에서 꺼낸 뒤 출력하기 전에 프로세스가 끝나지 않도록 잠시 기다린다
            watcher.join(timeout=1)


if __name__ == "__main__":
    sys.exit(main())
