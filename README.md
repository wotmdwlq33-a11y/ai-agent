# Jev — 개인 비서 (Jev ↔ Claude 라우팅)

Jev는 요청을 받아 **간단한 것은 직접 처리**하고, 나머지는 **Claude API로 넘기는** 개인 비서입니다.

```
사용자 입력 ──► router.route()
                 ├─ local  : 시간 / 날짜 / 도움말 / 초기화  → API 호출 없음
                 └─ claude : effort 선택 후 Claude 호출
                              ├─ low    : 짧은 일상 대화 (20자 이하)
                              ├─ medium : 일반 요청
                              └─ high   : 코드·분석·설계 등 키워드, 또는 300자 이상
```

## 설계 메모
- **라우팅은 규칙 기반**입니다. 라우팅 판단에 API를 쓰지 않아 비용이 없고 결과가 항상 같습니다.
- 로컬 처리는 **문장 전체가 일치할 때만** 합니다. 예를 들어 "회의 몇 시야?"는 Claude로 보냅니다.
- Claude 모델은 환경변수 `JEV_MODEL`로 하나만 지정합니다. 모델을 바꾸는 대신 `effort`로 비용과 품질을 조절합니다.
- Claude가 안전 사유로 거절하면 서버가 다른 모델로 다시 시도합니다(`fallbacks="default"`). 그래도 거절되면 대화 기록에 남기지 않습니다.
- 대화 기록은 **뒤에 덧붙이기만** 하고, Claude 응답 블록은 그대로 다시 보냅니다.

## 실행
```bash
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=...      # 또는 `ant auth login`
export JEV_MODEL=...              # 사용할 Claude 모델 ID
python -m jev                     # 대화 시작
python -m jev --debug             # 라우팅 결과도 함께 출력
pytest                            # 테스트 (API 키 불필요)
```

## 파일
| 파일 | 역할 |
|---|---|
| `jev/router.py` | 요청을 local / claude로 나누고 effort 결정 |
| `jev/local_skills.py` | 시간, 날짜, 도움말 (한국 시간 기준) |
| `jev/claude_client.py` | Claude API 호출, 거절과 길이 초과 처리 |
| `jev/assistant.py` | `Jev.handle()`: 라우팅 실행과 대화 기록 관리 |
| `jev/cli.py` | 터미널 REPL |
| `tests/` | 라우터와 비서 동작 테스트 (가짜 Claude 사용) |

## 다음 단계 후보
- 로컬 기능 추가 (메모, 알림 등)
- 규칙으로 판단하기 애매한 요청은 저렴한 분류 호출로 라우팅
- 스트리밍 응답
