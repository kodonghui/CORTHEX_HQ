# CORTHEX HQ — CIO 매매 흐름

> VSCode에서 `Ctrl+Shift+V` 누르시면 그림으로 보입니다.
> 비유: 주식 운용팀 회의. CIO(최고투자책임자)가 혼자 분석하면서, 동시에 4명 애널리스트에게도 분석 지시.

## CIO 매매 신호 생성 흐름

```mermaid
flowchart TD
    TRIGGER["📥 매매 분석 트리거\n- 대표님 직접 명령\n- 자동 스케줄 (크론)\n- 봇 run-now"]

    subgraph CIO_7STEP["🧠 CIO 7단계 독자분석 (병렬)"]
        direction TB
        S1["① 매크로 환경\n(macro_fed_tracker)"]
        S2["② 섹터 선택\n(sector_rotation)"]
        S3["③ 위기 감지\n(correlation_analyzer)"]
        S4["④ 시장 심리\n(sentiment_nlp)"]
        S5["⑤ 펀더멘탈\n(us_financial_analyzer\n+ sec_edgar)"]
        S6["⑥ 실적 리스크\n(earnings_ai)"]
        S7["⑦ 기술적 타이밍\n(us_technical_analyzer)"]
        S8["⑧ 옵션 확인\n(options_flow)"]
        S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7 --> S8
    end

    subgraph SPECIALISTS["👨‍💼 전문가 4명 동시 분석 (병렬)"]
        direction LR
        MCS["시황분석가\nmarket_condition\n→ 시장 환경"]
        SAS["펀더멘탈 분석가\nstock_analysis\n→ 실적·재무"]
        TAS["기술적 분석가\ntechnical_analysis\n→ 차트·지표"]
        RMS["리스크 관리자\nrisk_management\n→ 위험 요소"]
    end

    subgraph DATA_SOURCES["🌐 실시간 데이터"]
        KR["한국 주식\n(KIS API)"]
        US["미국 주식\n(SEC EDGAR\n/ Yahoo Finance)"]
        NEWS["뉴스\n(Naver / Web)"]
        MACRO["경제 지표\n(ECOS / Fed)"]
    end

    subgraph KELLY["⚖️ Kelly 비중 산출"]
        CALC["Kelly Criterion 계산\nf* = (b·p − q) / b\n25% 초과 → Half-Kelly\n음수 → 노포지션"]
        SIZE["포지션 크기 결정\n(order_size: CIO 자율)"]
    end

    subgraph DECISION["📋 최종 투자 결정"]
        MERGE["CIO 독자분석 + 전문가 4명\n전부 합산"]
        SIGNAL["매매 신호 생성\n{'ticker': 'NVDA',\n 'action': 'BUY',\n 'price': 189.115,\n 'reason': '...'}"]
    end

    subgraph EXECUTION["🚀 주문 실행"]
        MODE{"매매 모드"}
        MOCK["모의투자\n(paper_trading)\n실제 주문 없음"]
        REAL["실투자\nKIS API 주문\n(매수/매도)"]
    end

    subgraph RECORD["📁 기록 저장"]
        ARCHIVE["기밀문서\n(CIO 보고서)"]
        DB["SQLite DB\n(매매 이력)"]
        NOTION["노션\n(투자 일지)"]
        TELEGRAM["텔레그램\n(대표님 알림)"]
    end

    TRIGGER --> CIO_7STEP
    TRIGGER --> SPECIALISTS

    MCS --> DATA_SOURCES
    SAS --> DATA_SOURCES
    TAS --> DATA_SOURCES
    RMS --> DATA_SOURCES
    S1 --> DATA_SOURCES
    S5 --> DATA_SOURCES

    CIO_7STEP --> MERGE
    SPECIALISTS --> MERGE
    MERGE --> SIGNAL
    SIGNAL --> CALC
    CALC --> SIZE
    SIZE --> DECISION

    DECISION --> MODE
    MODE -->|"모의투자 ON"| MOCK
    MODE -->|"실투자 ON"| REAL

    MOCK --> RECORD
    REAL --> RECORD

    style TRIGGER fill:#fbbf24,stroke:#d97706,color:#000
    style CIO_7STEP fill:#d1fae5,stroke:#059669
    style SPECIALISTS fill:#ddd6fe,stroke:#7c3aed
    style KELLY fill:#fee2e2,stroke:#dc2626
    style REAL fill:#ef4444,stroke:#b91c1c,color:#fff
    style MOCK fill:#6ee7b7,stroke:#059669,color:#000
```

## 주요 도구 목록

| 구분 | 도구 | 용도 |
|------|------|------|
| 한국 | kr_stock, dart_monitor, stock_screener | 국내 주가·공시 |
| 미국 | sec_edgar, us_financial_analyzer, earnings_ai | 미국 실적·재무 |
| 기술 | us_technical_analyzer, chart_generator | 차트·지표 |
| 심리 | sentiment_nlp, options_flow | 시장 심리·옵션 |
| 거시 | macro_fed_tracker, global_market_tool | Fed·환율·경제 |
| 포트폴리오 | portfolio_optimizer_v2, financial_calculator | Kelly·비중 최적화 |

## 첫 실매매 기록

> 2026-02-21 04:38 KST — NVDA 1주 매수 @ $189.115 (첫 실거래 성공)
