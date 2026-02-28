# arm_server.py P4 리팩토링 — ARGOS 수집 분리

**빌드**: #660 | **날짜**: 2026-02-28

## 요약

arm_server.py에서 ARGOS 데이터 수집 로직(16함수 + 컨텍스트 빌더)을 `web/argos_collector.py`로 분리.

## 변경

| 파일 | 변경 |
|------|------|
| `web/argos_collector.py` | **신규** 1,026줄 — 수집 6종 + 래퍼 6개 + 오케스트레이터 + RL분석 + 컨텍스트빌더 |
| `web/arm_server.py` | 10,399→9,436줄 (-963줄) |
| `web/handlers/argos_handler.py` | 스텁 7개 삭제 → argos_collector 직접 import (505→472줄) |

## 리팩토링 누적

| Phase | 모듈 | 줄수 | 감소 |
|-------|------|------|------|
| P1 | config_loader.py | 343 | -294 |
| P2 | debug_handler.py | 591 | -515 |
| P3 | argos_handler.py | 505 | -429 |
| P4 | argos_collector.py | 1,026 | -963 |
| **합계** | **4개 모듈** | **2,465줄** | **-2,201줄** |

arm_server.py: 11,637 → 9,436줄 (19% 감소)
