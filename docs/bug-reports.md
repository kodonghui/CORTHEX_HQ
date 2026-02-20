# CORTHEX HQ 버그 리포트 모음

> 같은 실수 반복 방지용. 도구 개발 시 반드시 참고할 것.

---

## BUG-001: 도구 스키마 type:None → GPT-5.2 400 에러 (2026-02-20)

### 증상
- CIO(투자분석처장) + 4명 전문가 모듈 **전원** Error 400
- `Invalid schema for function 'cross_agent_protocol': schema must be a JSON Schema of 'type: "object"', got 'type: "None"'`
- 87개 도구 중 **1개만 잘못돼도 전체 도구 호출 실패**

### 원인
- `tools.yaml`의 parameters가 "평면(flat)" 형식일 때:
  ```yaml
  parameters:
    action:
      type: string
      required: true
    to_agent:
      type: string
  ```
- `_build_tool_schemas()`가 이걸 JSON Schema `{"type": "object", "properties": {...}}` 형식으로 변환하지 않고 그대로 전달
- 결과: `input_schema`에 `"type"` 키가 없음 → OpenAI가 `type: None`으로 인식 → 400 에러

### 수정
- `ai_handler.py`의 `_build_tool_schemas()`에 평면 → JSON Schema 자동 변환 로직 추가
- OpenAI 변환 부분에 안전장치 추가: `type != "object"`이면 강제 보정

### 교훈
1. **tools.yaml에 새 도구 추가 시**: parameters를 평면 형식으로 써도 OK (자동 변환됨)
2. **GPT-5.2 strict 모드 필수 조건**:
   - `"type": "object"` 반드시 있어야 함
   - `"properties"` 반드시 있어야 함
   - 모든 프로퍼티가 `"required"` 배열에 있어야 함
   - `"additionalProperties": false` 필수
3. **도구 1개의 스키마 에러 = 전체 도구 호출 실패** → 절대 방심 금지

---

## BUG-002: 배포마다 자동매매 봇 꺼짐 (2026-02-20)

### 증상
- 배포할 때마다 자동매매 봇이 OFF 상태로 리셋됨
- CEO가 매번 수동으로 다시 켜야 함

### 원인
- `_trading_bot_active = False`가 Python 전역 변수 — 서버 재시작 시 초기화
- DB에 상태를 저장하지 않았음

### 수정
- `toggle_trading_bot()`에서 `save_setting("trading_bot_active", ...)` 추가
- `on_startup()`에서 `load_setting("trading_bot_active")` 읽어서 자동 복원
- 봇이 켜진 상태였으면 서버 시작 시 자동으로 `_trading_bot_loop()` 재시작

### 교훈
- **서버 재시작 후에도 유지돼야 하는 상태**는 반드시 DB(`save_setting`)에 저장할 것
- Python 전역 변수는 프로세스가 죽으면 날아감
- 같은 패턴의 다른 변수가 있는지 확인: `_cron_task`, `_batch_poller_task` 등

---

## BUG-003: KIS 토큰 만료 — IS_MOCK 변경 후 (2026-02-20)

### 증상
- `KOREA_INVEST_IS_MOCK`을 true→false로 변경 후 "만료된 token" 에러

### 원인
- DB에 캐시된 모의투자 토큰이 실거래 서버에서 유효하지 않음

### 수정
- `get_balance()`에 토큰 만료 자동 재발급 로직 추가

### 교훈
- IS_MOCK 변경 시 반드시 토큰 캐시 무효화 필요

---

## BUG-004: KIS 미국주식 TR_ID 잘못 사용 (2026-02-20)

### 증상
- 미국주식 주문이 안 됨

### 원인
- TR_ID를 일본용(`TTTS0308U`)으로 잘못 사용

### 교훈
- **외부 API 코딩 시 반드시 WebSearch로 최신 공식 문서 확인** 후 코딩
- 기억에만 의존 금지
