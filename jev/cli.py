"""터미널에서 Jev와 대화하는 REPL."""

from __future__ import annotations

import argparse
import dataclasses
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import anthropic

from jev import config as config_mod
from jev import korean
from jev.assistant import Jev
from jev.config import ConfigError
from jev.memory import HistoryError
from jev.skills import reminders
from jev.skills.timeparse import format_korean_datetime
from jev.storage import StorageError

Output = Callable[[str], None]


def _print(text: str) -> None:
    print(text, flush=True)


def _write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="jev", description="Jev 개인 비서")
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
        return [f"(알림을 확인하지 못했어요: {e})"]
    return [f"⏰ 알림: {r.text} ({format_korean_datetime(r.due, current)})" for r in due]


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
    while True:
        for line in _due_reminders(cfg.data_dir):
            _print(line)
        try:
            text = input("나: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            continue
        respond(jev, text, stream=stream, debug=args.debug, out=_print, write=_write)


if __name__ == "__main__":
    sys.exit(main())
