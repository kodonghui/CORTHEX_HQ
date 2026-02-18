# BE 팀원 작업 보고

## 버전
3.01.001

## 작업 날짜
2026-02-18

## 브랜치
claude/autonomous-system-v3

---

## 수정 내용 요약

### 작업 1-1: CMO sns_manager 버그 (이미 해결됨)
- **확인 결과**: `config/agents.yaml` line 894에 `sns_manager`가 이미 CMO manager의 `allowed_tools`에 등록되어 있음
- **추가 조치 불필요**

### 작업 1-2: skill_social_content 400 오류 수정
- **수정 파일**: `src/llm/openai_provider.py`
- **원인**: GPT-5.2, GPT-5.2-pro 등 reasoning 모델은 OpenAI API에서 `max_tokens` 파라미터를 거부하고 `max_completion_tokens`를 요구함
- **수정 내용**: reasoning 모델 여부를 자동 감지하여 파라미터명 전환
  - `reasoning_effort`가 지정된 경우 또는 모델명에 `5.2`, `-o1`, `-o3`, `-o4`가 포함된 경우 → `max_completion_tokens` 사용
  - 그 외 일반 모델 → 기존 `max_tokens` 유지
- **영향 범위**: `skill_social_content`는 `gpt-5-mini` 모델 사용 → 직접 영향 없음. 하지만 GPT-5.2 계열 모델(CIO 투자분석처장 등)에서 동일 오류 방지

### 작업 2: delegation_log 테이블 + 협업 로그 API
- **수정 파일 1**: `web/db.py`
  - `delegation_log` 테이블 스키마를 `_SCHEMA_SQL`에 추가 (id, sender, receiver, message, task_id, log_type, created_at)
  - 인덱스 4개 추가 (sender, receiver, task_id, created_at)
  - `save_delegation_log()` 함수 추가 — 로그 1건 저장
  - `list_delegation_logs()` 함수 추가 — 최근순 조회, agent 파라미터로 필터 가능
- **수정 파일 2**: `web/mini_server.py`
  - `GET /api/delegation-log` 엔드포인트 추가 — 최근 100개 조회, `?agent=에이전트명`으로 필터
  - `POST /api/delegation-log` 엔드포인트 추가 — body: {sender, receiver, message, task_id?, log_type?}
  - `_delegate_to_specialists()` 함수에 위임 자동 기록 추가:
    - 처장이 전문가에게 위임할 때 → `log_type="delegation"`으로 자동 저장
    - 전문가 결과가 처장에게 반환될 때 → `log_type="report"`으로 자동 저장

### 작업 3: 도구 호출 횟수 기반 WebSocket 진행률 이벤트
- **수정 파일**: `web/mini_server.py`
- **수정 위치**: `_call_agent()` 내부의 `_tool_executor()` 클로저
- **추가 내용**:
  - `_MAX_TOOL_CALLS = 5` 상수 정의 (무한 루프 방지 기준값과 동일)
  - 도구 호출 1회마다 `agent_status` WebSocket 이벤트 발송
  - 이벤트 형식: `{"event": "agent_status", "data": {"agent_id": "xxx", "status": "working", "progress": 0.4, "detail": "도구명 실행 중...", "tool_calls": 2, "max_calls": 5}}`
  - 진행률 계산: `call_count / 5` (1회=20%, 2회=40%, 3회=60%, 4회=80%, 5회=100%)

---

## 수정한 파일 목록
| 파일 | 수정 내용 |
|------|---------|
| `src/llm/openai_provider.py` | reasoning 모델 max_completion_tokens 자동 전환 |
| `web/db.py` | delegation_log 테이블 + CRUD 함수 2개 추가 |
| `web/mini_server.py` | delegation-log API 2개 + 위임 자동 기록 + tool_calls WebSocket 이벤트 |
| `config/agents.json` | yaml2json.py 재실행으로 재생성 |
| `config/tools.json` | yaml2json.py 재실행으로 재생성 |
| `config/quality_rules.json` | yaml2json.py 재실행으로 재생성 |

## 현재 상태
모든 수정 완료. yaml2json.py 재실행 완료.

## 다음에 할 일
- 배포 후 서버에서 `/api/delegation-log` 응답 확인
- WebSocket 이벤트에서 `tool_calls` 필드가 프론트엔드에 표시되는지 확인 (FE 팀원 담당)
