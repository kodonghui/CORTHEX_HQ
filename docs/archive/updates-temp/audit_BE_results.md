# BE 전수검사 결과 보고서

## 버전
3.01.001 (패치: gpt-5.1 허가되지 않은 모델명 제거)

## 작업 날짜
2026-02-18

## 담당 파일
`web/mini_server.py` (총 7083줄 → 수정 후 7076줄)

---

## 전수검사 범위

파일 전체를 1500줄씩 6개 구간으로 나눠 Read 도구로 전부 읽음:

| 구간 | 범위 | 주요 내용 |
|------|------|---------|
| 1 | 1~1500줄 | imports, AGENTS 목록, WebSocket, 핵심 API |
| 2 | 1500~3000줄 | 배치 체인 오케스트레이터 |
| 3 | 3000~4500줄 | 트레이딩 시스템, 지식, 메모리, SNS |
| 4 | 4500~6000줄 | 품질 검수, 에이전트 설정, 모델 목록, 텔레그램 |
| 5 | 6000~7083줄 | Notion, 라우팅, 에이전트 파이프라인, 도구 실행 |

---

## 버그 발견 목록 (수정 완료)

### BUG-1: gpt-5.1 허가되지 않은 모델명 (수정 완료)

- **위치**: `mini_server.py` 4666줄, `get_available_models()` 함수 내부
- **문제**: `gpt-5.1`이 CLAUDE.md 허용 모델 목록에 없는 존재하지 않는 모델명
- **영향**: 사용자가 모델 선택 화면에서 이 모델을 선택하면 API 오류 발생
- **수정**: 해당 항목(7줄) 전체 삭제
- **검증**: `grep gpt-5\.1` → 0건 확인 완료

**삭제된 코드:**
```python
{
    "name": "gpt-5.1",
    "provider": "openai",
    "tier": "manager",
    "cost_input": 4.0,
    "cost_output": 20.0,
    "reasoning_levels": ["none", "low", "medium", "high"],
},
```

---

## 이상 없음 확인 목록

### 1. 금지 모델명 — 0건 확인

아래 금지 모델명이 mini_server.py에 존재하는지 grep 검사:

| 금지 모델명 | 검사 결과 |
|-----------|---------|
| `claude-haiku-4-6` | 0건 (없음) |
| `gpt-4o`, `gpt-4o-mini` | 0건 (없음) |
| `gpt-4.1`, `gpt-4.1-mini` | 0건 (없음) |
| `claude-sonnet-4-5-20250929` | 0건 (없음) |
| `gpt-5.1` | 0건 (수정으로 제거됨) |

### 2. API 중복 정의 — 없음

FastAPI에서 같은 경로 엔드포인트가 2번 정의되면 두 번째 것이 무시되는 문제.
주요 엔드포인트 grep 결과 모두 1건씩만 정의됨:
- `/api/tasks` — 1건
- `/api/batch` — 1건
- `/api/budget` — 1건
- `/api/dashboard` — 1건
- `/api/agents` — 1건

### 3. SNS 연결 상태 — 환경변수 기반 (이미 정상)

```python
# 4295~4313줄 — 하드코딩 False가 아니라 환경변수로 판단
_SNS_ENV_MAP = {
    "instagram": "INSTAGRAM_ACCESS_TOKEN",
    "youtube": "GOOGLE_CLIENT_ID",
    ...
}

@app.get("/api/sns/status")
async def get_sns_status():
    for p in _SNS_PLATFORMS:
        env_key = _SNS_ENV_MAP.get(p, "")
        has_key = bool(os.getenv(env_key, ""))  # 환경변수로 판단
        result[p] = {"connected": has_key, ...}
```

### 4. 비용 누적 (monthly_cost) — 정상

```python
# 677~693줄 — get_monthly_cost() 정상 사용
from db import get_monthly_cost
monthly = get_monthly_cost()
```

### 5. async/await 오류 — 없음

전체 파일에서 아래 오류 패턴 없음:
- `await await` (두 번 await) 없음
- async 함수에서 await 빠진 명백한 케이스 없음

### 6. AGENTS 목록 모델명 — 전부 허용 목록에 있음

줄 1~308의 AGENTS 리스트 28개 에이전트 모두 허용 모델 사용:
- `claude-sonnet-4-6`, `claude-opus-4-6` (Anthropic)
- `gpt-5.2-pro`, `gpt-5.2` (OpenAI)
- `gemini-3-pro-preview` (Google)

---

## 확인 필요 항목 (BE 단독으로 해결 불가)

### 주의-1: /api/operations 와 /api/commander 엔드포인트 없음

- **발견**: `mini_server.py`에 `/api/operations` 또는 `/api/commander` 경로가 **존재하지 않음**
- **grep 결과**: 0건
- **의미**: 프론트엔드(index.html)의 "작전현황" 탭과 "사령관실" 탭이 이 API를 호출한다면 404 오류 발생
- **조치 필요**: FE 팀에서 index.html을 확인하여 실제로 이 API를 호출하는 코드가 있는지, 있다면 어떤 데이터가 필요한지 파악 후 BE 구현 필요

---

## 수정 파일 목록

| 파일 | 수정 내용 | 줄 |
|------|---------|---|
| `web/mini_server.py` | `gpt-5.1` 허가되지 않은 모델 항목 삭제 (7줄 제거) | 4665~4672 |
| `config/models.yaml` | `gpt-5.1` 모델 항목 삭제 (7줄 제거) | 25~31 |
| `src/tools/token_counter.py` | `_MODEL_ENCODINGS`에서 `gpt-5.1` 매핑 삭제 (1줄 제거) | 28 |

---

## 현재 상태

- BE 전수검사 완료
- BUG-1 수정 완료 및 grep 검증 완료
- `/api/operations`, `/api/commander` 미구현 상태 — FE 팀 확인 후 추가 구현 여부 결정 필요

---

## 다음에 할 일

1. FE 팀에서 `index.html`의 "작전현황", "사령관실" 탭이 어떤 API를 호출하는지 확인
2. 필요하다면 BE에서 해당 API 엔드포인트 신규 구현
3. `config/models.yaml`에도 `gpt-5.1`이 있는지 CONFIG 팀 확인 필요
