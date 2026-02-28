# arm_server.py P7 리팩토링 — 스케줄러 분리

**빌드**: #667 | **날짜**: 2026-02-28

## 요약

arm_server.py에서 크론 실행 엔진 + 워크플로우 실행 + Soul Gym 루프를 `web/scheduler.py`로 분리.

## 변경

| 파일 | 변경 |
|------|------|
| `web/scheduler.py` | **신규** 508줄 — 크론엔진 + 워크플로우 + Soul Gym + 백그라운드태스크 |
| `web/arm_server.py` | 4,948→4,509줄 (-439줄) |

## 이관된 기능

- **크론 엔진**: 표현식 파서/매처 (5필드 리눅스 표준), 프리셋 변환
- **크론 루프**: 1분 주기 (ARGOS 수집, 환율 갱신, 사용자 예약, 가격 트리거)
- **기본 스케줄**: CIO 일일/주간 자동 등록, CSO→CIO 마이그레이션
- **예약 실행**: @멘션 파싱 → AI 처리 → 텔레그램 CEO 발송
- **워크플로우**: 순차 실행 API + WebSocket 진행 알림
- **Soul Gym**: 24/7 상시 진화 루프 (30분 간격)
- **start_background_tasks()**: on_startup 스케줄링 11개 태스크 통합

## 리팩토링 누적

| Phase | 모듈 | 줄수 | 감소 |
|-------|------|------|------|
| P1 | config_loader.py | 343 | -294 |
| P2 | debug_handler.py | 591 | -515 |
| P3 | argos_handler.py | 505 | -429 |
| P4 | argos_collector.py | 1,026 | -963 |
| P5 | batch_system.py | 1,808 | -1,760 |
| P6 | trading_engine.py | 2,830 | -2,728 |
| P7 | scheduler.py | 508 | -439 |
| **합계** | **7개 모듈** | **7,611줄** | **-7,128줄** |

arm_server.py: 11,637 → 4,509줄 (61% 감소)
