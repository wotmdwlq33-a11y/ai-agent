"""터미널에서 Jev와 대화하는 REPL."""

from __future__ import annotations

import sys

import anthropic

from jev.assistant import Jev


def main() -> None:
    debug = "--debug" in sys.argv
    jev = Jev()
    print('Jev: 안녕하세요! 도움말은 "/help", 종료는 Ctrl+D 입니다.')
    while True:
        try:
            text = input("나: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not text:
            continue
        try:
            answer = jev.handle(text)
        except anthropic.AuthenticationError:
            print("Jev: Claude 인증에 실패했어요. ANTHROPIC_API_KEY를 확인해 주세요.")
            continue
        except anthropic.RateLimitError:
            print("Jev: 요청이 너무 많아요. 잠시 후 다시 시도해 주세요.")
            continue
        except anthropic.APIStatusError as e:
            print(f"Jev: Claude API 오류가 났어요 ({e.status_code}).")
            continue
        except anthropic.APIConnectionError:
            print("Jev: 네트워크 연결을 확인해 주세요.")
            continue
        if debug:
            r = answer.route
            print(f"  [route] {r.target} skill={r.skill} effort={r.effort} ({r.reason})")
        print(f"Jev: {answer.text}")


if __name__ == "__main__":
    main()
