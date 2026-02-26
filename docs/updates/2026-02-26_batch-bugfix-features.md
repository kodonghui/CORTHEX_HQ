# 2026-02-26 일괄 버그수정 + 신규 기능 + 명칭 정리

> 세션 3: ARGOS 후속 작업 + R 시리즈 버그 수정 + N 시리즈 새 기능

## 버그 수정 (R 시리즈)

### R-1: 대화 비우기 후 목록 잔존
- **원인**: PATCH `/api/conversation/sessions/{id}` (is_active=0) 실패 시 클라이언트에서 목록 제거하지만, 새로고침하면 서버 데이터 기준으로 다시 나타남
- **수정**: PATCH 응답 확인 → 실패 시 DELETE로 폴백
- **파일**: `web/static/js/corthex-app.js` (clearConversation)

### R-4: 통신국 ".env 없다고 뜸"
- **원인**: UI 텍스트가 ".env"라고 표시하지만 서버는 corthex.env 사용 (os.getenv()). 코드 로직은 정상
- **수정**: "서버 .env" → "서버 환경변수"로 문구 변경
- **파일**: `web/templates/index.html` (SNS 연결 상태 탭)

### R-6: 장기기억 UI 접근성
- **원인**: "기억" 버튼이 10px 텍스트로 너무 작음, 설명 없음
- **수정**: 버튼 크기 증가 (text-xs, px-3 py-1.5, 아이콘 추가) + 테이블 위 안내 텍스트 추가
- **파일**: `web/templates/index.html` (전력분석 탭)

## 신규 기능 (N 시리즈)

### N-3: 정보국 드래그앤드롭 파일 업로드
- 파일 트리 패널에 dragover/drop 이벤트 추가
- 드래그 시 시각적 오버레이 (점선 테두리 + 아이콘)
- 허용 형식: .md, .txt, .yaml, .json, .csv (나머지 거부 + 토스트 안내)
- **파일**: `index.html` (knowledge 탭), `corthex-app.js` (handleKnowledgeDrop)

### N-4: 진화시스템 웹 실시간 로그
- **서버**: `_broadcast_evolution_log()` 헬퍼 + `/api/evolution/logs` REST API (activity_logs에서 Soul Gym 필터)
- **클라이언트**: WebSocket `evolution_log` 이벤트 핸들러 + 전력분석 탭 EVOLUTION LOG 패널
- 실시간 로그 표시: 시간/레벨(색상 도트)/메시지 + 새로고침 버튼
- **파일**: `arm_server.py`, `corthex-app.js`, `index.html`

### N-5: 피드백 모드 피그마급 재구현
- **기존**: 드래그 사각형 + prompt() 팝업
- **변경**: 클릭 → 말풍선 핀 생성 + 인라인 textarea 입력 (Ctrl+Enter 전송)
- 핀 목록 사이드 패널 (최근 5개 + 개별/전체 삭제)
- 핀 번호가 화면에 표시 (노란 동그라미)
- **파일**: `corthex-app.js`, `index.html`

## 명칭 정리 (C-1)
- "처장" → "팀장" 35곳 주석/로그/문자열 변경 (변수명 유지)
- 대상: config/agents.yaml, tools.yaml, quality_rules.yaml, src/ 하위, web/ 하위

## ARGOS 후속 (세션 2에서 계속)
- PR#624: 타임아웃 수정 (per-ticker 20s + 7/3일 단축)
- PR#625: 순차 수집 (_argos_sequential_collect, DB lock 방지)
- 서버 클로드: ARGOS 실시간 디버깅 별도 진행 중

## 수정 파일 목록
- `web/templates/index.html` — R-6, R-4, N-3, N-4, N-5
- `web/static/js/corthex-app.js` — R-1, N-3, N-4, N-5
- `web/arm_server.py` — N-4 (evolution log broadcast + REST API)
- `config/agents.yaml` — 명칭 정리
- `config/tools.yaml` — 명칭 정리
- `config/quality_rules.yaml` — 명칭 정리
- `src/` 하위 여러 파일 — 명칭 정리
- `docs/project-status.md` — 업데이트
- `docs/todo/BACKLOG.md` — 업데이트
