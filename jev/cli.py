"""터미널에서 Jev와 대화하는 REPL."""

from __future__ import annotations

import argparse
import dataclasses
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

import anthropic

from jev import config as config_mod
from jev.assistant import Jev
from jev.config import ConfigError
from jev.memory import HistoryError

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
    return parser.parse_args(argv)


def _due_reminders(data_dir: Path) -> list[str]:
    """시간이 된 알림 문구를 꺼낸다. 알림 기능이 없거나 실패해도 대화는 계속한다."""
    try:
        from jev.skills import reminders
    except ImportError:
        return []
    try:
        due = reminders.pop_due(data_dir, datetime.now().astimezone())
    except Exception as e:  # 알림 파일 문제로 REPL이 멈추면 안 된다
        return [f"(알림을 확인하지 못했어요: {e})"]
    return [f"⏰ 알림: {r.text} ({r.due:%m월 %d일 %H시 %M분})" for r in due]


def respond(jev: Jev, text: str, *, stream: bool, debug: bool, out: Output, write: Output) -> None:
    """입력 한 줄을 처리하고 결과를 출력한다. 오류는 사용자에게 알리고 계속 진행한다."""
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
        return
    except ConfigError as e:
        out(f"\nJev: 설정 오류 — {e}" if started else f"Jev: 설정 오류 — {e}")
        return
    except anthropic.AuthenticationError:
        out("Jev: Claude 인증에 실패했어요. ANTHROPIC_API_KEY를 확인해 주세요.")
        return
    except anthropic.RateLimitError:
        out("Jev: 요청이 너무 많아요. 잠시 후 다시 시도해 주세요.")
        return
    except anthropic.APIStatusError as e:
        out(f"Jev: Claude API 오류가 났어요 ({e.status_code}).")
        return
    except anthropic.APIConnectionError:
        out(("\n" if started else "") + "Jev: 네트워크 연결을 확인해 주세요.")
        return
    except HistoryError as e:
        out(f"\nJev: {e}")
        return

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
