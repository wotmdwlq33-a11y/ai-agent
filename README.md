# Jev — 개인 비서 (Jev ↔ Claude 라우팅)

Jev는 요청을 받아 **간단한 것은 직접 처리**하고, 나머지는 **Claude API로 넘기는** 개인 비서입니다.
시간·날짜·메모·알림·단위 변환·공휴일 같은 요청은 API 호출 없이 바로 답하고,
그 밖의 질문만 Claude에게 보냅니다.

## 구조

```mermaid
flowchart TD
    U[사용자 입력] --> CLI["cli.py<br/>REPL · 스트리밍 출력 · 알림 확인"]
    CLI --> J["assistant.py<br/>Jev.handle()"]
    J --> R{"router.py<br/>route()"}
    R -- "local (문장 전체 일치)" --> L["local_skills.py"]
    L --> S1["skills/memo.py<br/>메모"]
    L --> S2["skills/timeparse.py · reminders.py<br/>시간 해석 · 알림"]
    L --> S3["skills/units.py<br/>단위 변환"]
    L --> S4["skills/holidays.py<br/>공휴일 · 날짜"]
    R -- "claude (effort: low/medium/high)" --> C["claude_client.py<br/>ask / ask_stream"]
    C --> API[(Claude API)]
    J <--> M["memory.py<br/>대화 기록 JSON"]
    CFG["config.py<br/>환경변수 · .env"] -.-> CLI
    CFG -.-> J
    S1 & S2 & M --> D[("데이터 폴더<br/>~/.jev")]
```

```
사용자 입력 ──► router.route()
                 ├─ local  : 시간 / 날짜 / 도움말 / 초기화 / 메모 / 알림 / 단위 변환 / 공휴일
                 │           → API 호출 없음
                 └─ claude : effort 선택 후 Claude 호출 (기본은 스트리밍 출력)
                              ├─ low    : 짧은 일상 대화 (20자 이하)
                              ├─ medium : 일반 요청
                              └─ high   : 코드·분석·설계 등 키워드, 또는 300자 이상
```

## 설치와 실행

```bash
pip install -e ".[dev]"
cp .env.example .env              # 필요한 값을 채우세요 (.env는 git에 올라가지 않음)
export ANTHROPIC_API_KEY=...      # 또는 `ant auth login`
export JEV_MODEL=...              # 사용할 Claude 모델 ID (Claude를 부를 때만 필요)
python -m jev                     # 대화 시작 (답변을 스트리밍으로 출력)
python -m jev --debug             # 라우팅 결과도 함께 출력
python -m jev --no-stream         # 답변을 한 번에 출력
python -m jev --no-memory         # 대화 기록을 파일에 저장하지 않음
python -m jev --env-file my.env   # 다른 .env 파일 사용
```

로컬 기능만 쓸 때는 API 키와 `JEV_MODEL` 없이도 동작합니다.

## 사용 예

<!-- LOCAL_SKILLS -->

그 밖의 질문(예: "이번 주말 서울 근교 여행지 추천해 줘")은 Claude에게 넘깁니다.
"메모 앱 추천해 줘"처럼 로컬 기능과 비슷하지만 다른 맥락이 붙은 문장도 Claude로 보냅니다.

## 설정

환경변수 또는 `.env` 파일로 설정합니다. **이미 설정된 환경변수가 `.env`보다 우선**합니다.
값이 잘못되면 어떤 변수가 왜 잘못됐는지 알려 주고 종료합니다(종료 코드 2).

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `JEV_MODEL` | (없음) | Claude 모델 ID. Claude를 호출할 때만 필요 |
| `JEV_HOME` | `~/.jev` | 대화 기록·메모·알림을 저장할 폴더 |
| `JEV_MEMORY` | `on` | 대화 기록을 파일에 저장할지 (`on`/`off`) |
| `JEV_MAX_HISTORY_MESSAGES` | `40` | 보관·전송할 대화 메시지 최대 개수 |
| `JEV_MAX_HISTORY_BYTES` | `200000` | 대화 기록 JSON 최대 크기(바이트) |
| `JEV_MAX_TOKENS` | `16000` | Claude 응답 최대 토큰 |
| `JEV_STREAM` | `on` | 답변을 스트리밍으로 출력할지 |
| `JEV_ENV_FILE` | `./.env` | 읽을 `.env` 파일 경로 |

## 데이터 폴더 (`JEV_HOME`)

| 파일 | 내용 |
|---|---|
| `history.json` | Claude와의 대화 기록 (`/reset` 또는 "초기화"로 삭제) |
| `memos.json` | 메모 |
| `reminders.json` | 알림 |

파일은 임시 파일에 쓴 뒤 교체하는 방식으로 저장해서, 저장 도중 끊겨도 깨지지 않습니다.
대화 기록 파일이 깨져 있으면 `history.corrupt.json`으로 옮겨 두고 새로 시작합니다.

## 설계 메모
- **라우팅은 규칙 기반**입니다. 라우팅 판단에 API를 쓰지 않아 비용이 없고 결과가 항상 같습니다.
- 로컬 처리는 **문장 전체가 일치할 때만** 합니다. 예를 들어 "회의 몇 시야?"는 Claude로 보냅니다.
- Claude 모델은 환경변수 `JEV_MODEL`로 하나만 지정합니다. 모델을 바꾸는 대신 `effort`로 비용과 품질을 조절합니다.
- Claude가 안전 사유로 거절하면 서버가 다른 모델로 다시 시도합니다(`fallbacks="default"`). 그래도 거절되면 대화 기록에 남기지 않습니다.
  스트리밍 중 거절되면 이미 출력된 부분 답변은 무효라고 안내합니다.
- 대화 기록은 평소에는 **뒤에 덧붙이기만** 하고, Claude 응답 블록은 그대로 다시 보냅니다.
- 대화 기록이 한도(`JEV_MAX_HISTORY_*`)를 넘으면 오래된 턴부터 지워 **한도의 절반까지** 한 번에 줄입니다.
  이때와 파일에서 기록을 불러올 때는 **thinking 블록을 빼고 텍스트만** 남깁니다.
  앞부분이 바뀐 대화에 예전 thinking 블록을 다시 보내면 API가 거부할 수 있기 때문입니다.
- 테스트는 가짜 Claude 클라이언트(`tests/fakes.py`)를 써서 **실제 API를 호출하지 않습니다.**

## 개발

```bash
python -m ruff check .            # 린트
python -m ruff format --check .   # 포맷 검사
python -m mypy                    # 타입 검사 (strict)
python -m pytest -q               # 테스트 (API 키 불필요)
```

GitHub Actions(`.github/workflows/ci.yml`)가 Python 3.11 / 3.12 / 3.13에서 위 검사를 모두 실행합니다.

## 파일
| 파일 | 역할 |
|---|---|
| `jev/router.py` | 요청을 local / claude로 나누고 effort 결정 |
| `jev/local_skills.py` | 로컬 기능 실행과 답변 문구 (한국 시간 기준) |
| `jev/skills/memo.py` | 메모 추가·목록·검색 (`memos.json`) |
| `jev/skills/timeparse.py` | "10분 뒤", "내일 9시" 같은 한국어 시간 표현 해석 |
| `jev/skills/reminders.py` | 알림 저장과 시간이 된 알림 꺼내기 (`reminders.json`) |
| `jev/skills/units.py` | 길이·무게·온도·넓이·부피 단위 변환 |
| `jev/skills/holidays.py` | 대한민국 공휴일 표(2025–2027)와 조회 |
| `jev/claude_client.py` | Claude API 호출(일반·스트리밍), 거절과 길이 초과 처리 |
| `jev/memory.py` | 대화 기록 저장·불러오기·크기 제한 |
| `jev/config.py` | 환경변수와 `.env` 설정 읽기, 오류 메시지 |
| `jev/assistant.py` | `Jev.handle()`: 라우팅 실행과 대화 기록 관리 |
| `jev/cli.py` | 터미널 REPL |
| `tests/` | 테스트 (가짜 Claude 사용) |

## 공휴일 데이터 주의
- 2025–2027년만 들어 있습니다. 그 밖의 연도는 "지원하지 않는 연도"라고 답합니다.
- 음력 공휴일과 대체공휴일, 임시공휴일·선거일은 공개 발표(우주항공청 월력요항, 인사혁신처 등)를 바탕으로
  표로 넣었습니다. 출처는 `jev/skills/holidays.py` 상단에 있습니다.
- 이후 새로 지정되는 임시공휴일이나 재·보궐 선거일은 빠져 있을 수 있습니다.

## 다음 단계 후보
- 규칙으로 판단하기 애매한 요청은 저렴한 분류 호출로 라우팅
- 알림을 REPL 입력 대기 중에도 띄우기 (현재는 다음 입력 직전에 표시)
- 공휴일 데이터 연도 확장
