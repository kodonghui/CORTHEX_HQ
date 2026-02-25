# 텔레그램 기능 추가 — 주요 AI 명령어 5개

## 버전
3.03.002

## 작업 날짜
2026-02-18

## 작업 브랜치
claude/autonomous-system-v3

---

## 작업 배경

웹 UI에서는 `/심층토론`, `/전체`, `/순차`, `@에이전트` 등의 명령어를 쓸 수 있었지만,
텔레그램에서는 전혀 사용할 수 없었음.

텔레그램 봇에서도 웹 슬래시 명령어와 동일하게 사용 가능하도록 추가.

---

## 수정 파일
`web/arm_server.py` (단 하나의 파일만 수정)

---

## 추가된 기능

### 1. `/토론 [주제]` — 임원 토론 (2라운드)
- 처장 6명이 독립 의견 → 상호 재반박 (2라운드)
- 비서실장이 최종 종합
- 예: `/토론 AI가 인간의 일자리를 대체할까?`

### 2. `/심층토론 [주제]` — 심층 임원 토론 (3라운드)
- 처장 6명 × 3라운드 (더 깊은 반박)
- 예: `/심층토론 CORTHEX 2026 전략 방향`

### 3. `/전체 [메시지]` — 29명 전체 에이전트 동시 지시
- 6개 부서 처장 + 전문가들에게 동시 브로드캐스트
- 예: `/전체 전체 출석 보고`, `/전체 2026년 사업 현황 점검`

### 4. `/순차 [작업]` — 에이전트 릴레이 순차 협업
- 처장들이 순서대로 이전 작업 결과를 이어받아 작업
- 예: `/순차 CORTHEX 웹사이트 기술→보안→사업성 분석`

### 5. `@에이전트명 [지시]` — 특정 에이전트 직접 지시
- `@` 뒤에 agent_id 앞부분을 입력하면 자동 매핑
- 예: `@cto_manager 기술 스택 분석해줘`
- 예: `@cio 삼성전자 주식 분석해줘` (cio로 시작하는 에이전트 자동 매핑)

---

## 기술 구현 상세

### 문제
기존 `handle_message`에서 `/토론`, `/심층토론`, `/전체`, `/순차` 는 모두 `/` 로 시작하는 명령어.
텔레그램에서 `/`로 시작하는 메시지는 `filters.COMMAND`로 분류되어
`MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)`에서 처리되지 않음.
→ 웹에서는 작동하는 명령어가 텔레그램에서는 조용히 무시됨.

### 해결
각 명령어에 대해 `CommandHandler`를 별도 등록:
```python
_telegram_app.add_handler(CommandHandler("토론", cmd_debate))
_telegram_app.add_handler(CommandHandler("심층토론", cmd_deep_debate))
_telegram_app.add_handler(CommandHandler("전체", cmd_broadcast_all))
_telegram_app.add_handler(CommandHandler("순차", cmd_sequential))
```

### 장기 실행 백그라운드 처리
토론/전체/순차 명령은 2~10분 소요 → 즉시 "시작 중" 메시지 보내고 백그라운드 실행:
```python
async def _tg_long_command(update_obj, task_text, target_agent_id=None):
    # 즉시 "⏳ 시작 중" 메시지 전송
    # asyncio.create_task()로 백그라운드 실행
    # 완료 시 _telegram_app.bot.send_message()로 결과 전송
```

### @에이전트 파싱
`handle_message`에 @멘션 감지 로직 추가:
- `@cto` → `AGENTS`에서 `agent_id.startswith("cto")` 매핑 → `cto_manager`
- 매핑 성공 시 `target_agent_id`를 `_process_ai_command()`에 전달
- 매핑 실패 시 "에이전트를 찾을 수 없습니다" 안내

---

## 현재 상태
- 5개 기능 모두 구현 완료
- `web/arm_server.py` 1개 파일만 수정
- 배포 후 텔레그램에서 바로 사용 가능
