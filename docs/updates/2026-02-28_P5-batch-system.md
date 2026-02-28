# arm_server.py P5 리팩토링 — 배치 시스템 분리

**빌드**: #661 | **날짜**: 2026-02-28

## 요약

arm_server.py에서 배치 시스템+배치 체인 오케스트레이터 전체를 `web/batch_system.py`로 분리.

## 변경

| 파일 | 변경 |
|------|------|
| `web/batch_system.py` | **신규** 1,808줄 — 배치 큐 + AI Batch API + 배치 체인 4단계 + 폴러 |
| `web/arm_server.py` | 9,436→7,676줄 (-1,760줄) |

## 이관된 기능

- **배치 큐**: submit_batch, _run_batch, clear_batch_queue (3개 엔드포인트)
- **AI Batch API**: submit_ai_batch, check_batch_status, flush 등 (7개 엔드포인트)
- **배치 체인 4단계**: 분류 → 팀장 지시서 → 전문가 배치 → 종합 보고서
- **폴러**: _batch_poller_loop (60초 간격), _advance_batch_chain (상태머신)
- **상수**: _BATCH_CLASSIFY_PROMPT, _DELEGATION_PROMPT, _BATCH_MODE_SUFFIX

## 의존성 전략

- db, config_loader, ai_handler, ws_manager → 직접 import (순환 없음)
- arm_server.py 공유 함수 → `_ms()` 패턴 (15개: _AGENT_NAMES, _broadcast_status 등)

## 리팩토링 누적

| Phase | 모듈 | 줄수 | 감소 |
|-------|------|------|------|
| P1 | config_loader.py | 343 | -294 |
| P2 | debug_handler.py | 591 | -515 |
| P3 | argos_handler.py | 505 | -429 |
| P4 | argos_collector.py | 1,026 | -963 |
| P5 | batch_system.py | 1,808 | -1,760 |
| **합계** | **5개 모듈** | **4,273줄** | **-3,961줄** |

arm_server.py: 11,637 → 7,676줄 (34% 감소)
