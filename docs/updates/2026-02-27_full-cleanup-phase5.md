# 2026-02-27 — 버그 수정 + Phase 5 일괄 구현

## 요약
R-3/R-5 버그 수정 + NEXUS 2D 분할뷰 재설계 + Soul Gym 6팀장 확장을 한번에 배포.

## 변경 내역

### 🔴 R-3: 전력분석 데이터 안 나오는 버그
- **원인**: `create_task()`에 `agent_id`가 없어서 `/api/performance` 쿼리(`WHERE agent_id IS NOT NULL`)에 걸리지 않음
- **수정**: `update_task()`에 `agent_id=` 파라미터 추가 (6곳)
  - bg 완료/실패, 배치 아이템 완료, 크론 명령, 워크플로우 스텝, 텔레그램 장문/실시간
- **파일**: `web/arm_server.py`

### 🔴 R-5: 레이스 컨디션 수정
- **원인**: ARGOS 수집 `_argos_seq_running` bool, Soul Gym `_soul_gym_running` bool → TOCTOU 위험
- **수정**: `bool` 플래그 → `asyncio.Lock()` 전환
  - `_argos_seq_lock`: ARGOS 순차 수집 동시 실행 방지
  - `_soul_gym_lock`: Soul Gym 루프 중복 실행 방지
  - `state.py`: `bg_lock`, `batch_lock` 추가 (선언, 추후 적용 확대)
- **파일**: `web/arm_server.py`, `web/state.py`

### ✅ 5-1: NEXUS 2D 분할뷰 재설계
- **3D ForceGraph 모드 제거** (3D-force-graph CDN + 관련 JS 함수)
- **분할 뷰(split) 모드 추가**: 왼쪽 Mermaid 플로우차트 + 오른쪽 Drawflow 캔버스
- 기존 Mermaid/Canvas 단독 모드는 유지
- **파일**: `web/static/js/corthex-app.js`, `web/templates/index.html`

### ✅ 5-2: Soul Gym 6팀장 확장
- **`config/soul_gym_benchmarks.yaml`** (신규): 6팀장별 맞춤 벤치마크 문항
  - CIO: 기존 관심종목 분석 방식 유지
  - CSO/CLO/CMO/CPO/비서실장: 각 3문항씩 전문 영역 시험
- **`web/soul_gym_engine.py`** 전면 개편:
  - `GYM_TARGET_AGENTS` 6팀장 전체로 확장
  - `COST_CAP_USD` 20→50
  - `run_benchmark()` 디스패처 패턴으로 분리
  - `judge_response()` watchlist/question 별도 채점 함수
  - 루프 간격 5분→30분 (6팀장 순차 고려)

## 수정 파일
| 파일 | 변경 |
|------|------|
| `web/arm_server.py` | R-3 agent_id 6곳 + R-5 asyncio.Lock 2곳 |
| `web/state.py` | bg_lock, batch_lock 추가 |
| `web/soul_gym_engine.py` | 전면 개편 (~420줄) |
| `config/soul_gym_benchmarks.yaml` | 신규 (6팀장 벤치마크) |
| `web/static/js/corthex-app.js` | NEXUS 3D→split 전환 |
| `web/templates/index.html` | NEXUS 분할뷰 HTML |
