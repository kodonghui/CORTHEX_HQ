# CORTHEX HQ — 코드 구조 다이어그램

> 마지막 업데이트: 2026-02-28 (P7 완료 기준)

```mermaid
graph TD
    subgraph MAIN["🏛️ arm_server.py (메인 로비) — 4,509줄"]
        ENTRY["FastAPI 앱 시작점\n라우터 마운트\n에이전트 라우팅 P8 예정"]
    end

    subgraph SPLIT_V4["📦 v4 리팩토링으로 분리된 엔진들 (P1~P7)"]
        CFG["⚙️ config_loader.py\n설정·에이전트 로딩\n343줄 (P1)"]
        ARGOS["🔭 argos_collector.py\n뉴스·시황 수집\n1,026줄 (P4)"]
        BATCH["🏭 batch_system.py\n배치 분석·체인\n1,808줄 (P5)"]
        TRADE["📈 trading_engine.py\n매매·CIO 엔진\n2,830줄 (P6)"]
        SCHED["⏰ scheduler.py\n스케줄·Soul Gym\n508줄 (P7)"]
        ROUTER["🧠 agent_router.py\n에이전트 라우팅\n~1,900줄 ← P8 예정"]
    end

    subgraph HANDLERS["🚪 handlers/ — HTTP 접수 창구 28개 (v3 리팩토링)"]
        H_TRADE["trading_handler.py"]
        H_AGENT["agent_handler.py"]
        H_DEBUG["debug_handler.py (P2)"]
        H_ARGOS["argos_handler.py (P3)"]
        H_ETC["activity / schedule / sns\nnotion / knowledge / auth\n등 22개 더..."]
    end

    subgraph CORE["🔧 핵심 공통 모듈 (기존)"]
        AI["🤖 ai_handler.py\nClaude API 호출"]
        KIS["💰 kis_client.py\n증권사 API"]
        DB["🗄️ db.py\nSQLite 데이터베이스"]
        WS["📡 ws_manager.py\n실시간 WebSocket"]
        STATE["📊 state.py\n전역 상태 관리"]
        AGORA["🏛️ agora_engine.py\n회의·토론 엔진"]
        SOUL["💪 soul_gym_engine.py\nSoul Gym 엔진"]
    end

    ENTRY --> CFG
    ENTRY --> HANDLERS
    ENTRY --> SPLIT_V4

    BATCH --> AI
    TRADE --> AI
    TRADE --> KIS
    ARGOS --> AI
    ROUTER --> AI
    SCHED --> BATCH

    H_TRADE --> TRADE
    H_AGENT --> ROUTER
    H_ARGOS --> ARGOS
    H_DEBUG --> DB

    AI --> WS
    ENTRY --> STATE
    ENTRY --> DB
    AGORA --> AI
    SOUL --> AI

    style MAIN fill:#1e3a5f,color:#fff
    style SPLIT_V4 fill:#1a3a1a,color:#fff
    style HANDLERS fill:#3a1a1a,color:#fff
    style CORE fill:#2a2a2a,color:#fff
    style ROUTER fill:#5f3a00,color:#fff,stroke:#ff9900,stroke-width:2px
```

## 비유로 보는 구조

```
corthex-hq.com
      ↓
arm_server.py (로비 — 안내·연결만)
      ↓
┌─────────────────────────────────────────┐
│ handlers/ (접수 창구 28개)              │
│  요청 받아서 → 엔진으로 전달            │
└─────────────────────────────────────────┘
      ↓
┌─────────────────────────────────────────┐
│ 엔진들 (실제 일하는 곳)                │
│  trading_engine.py  — 매매 결정         │
│  batch_system.py    — 분석 공장         │
│  scheduler.py       — 시간 관리         │
│  argos_collector.py — 정보 수집         │
│  agent_router.py    — 에이전트 지휘 (P8)│
└─────────────────────────────────────────┘
      ↓
┌─────────────────────────────────────────┐
│ 공통 도구들                             │
│  ai_handler.py  — Claude API            │
│  kis_client.py  — 증권사 연결           │
│  db.py          — 데이터 저장           │
│  ws_manager.py  — 실시간 화면 업데이트 │
└─────────────────────────────────────────┘
```

## 줄수 변화 (v4 기준)

| 시점 | arm_server.py | 비고 |
|------|--------------|------|
| v4 시작 | 11,637줄 | 모든 것이 한 파일 |
| P1~P7 완료 | 4,509줄 | 7개 모듈 분리 |
| P8 완료 후 | ~300줄 (예상) | 얇은 로비만 남음 |
