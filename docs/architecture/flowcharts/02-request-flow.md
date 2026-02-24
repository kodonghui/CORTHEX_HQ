# CORTHEX HQ — 명령 처리 흐름

> VSCode에서 `Ctrl+Shift+V` 누르시면 그림으로 보입니다.
> 비유: 군 지휘 체계. 대통령(대표님) 명령 → 참모총장(비서실장) → 각 사령관(처장) → 부대원(전문가)

## 명령 처리 전체 흐름

```mermaid
flowchart TD
    INPUT["👤 대표님 명령 입력\n예: '오늘 시황 분석해줘'"]

    subgraph ENTRY["📥 입력 채널"]
        WEB["웹 사령관실\n(POST /api/command)"]
        TELEGRAM["텔레그램 봇"]
        SCHEDULE["자동 스케줄\n(크론 기지)"]
        WORKFLOW["워크플로우\n(자동화 탭)"]
    end

    subgraph ROUTING["🔀 Level 1~4 라우팅 판별"]
        L1["Level 1\n비서실장이 직접 답변\n(간단한 질문/지시)"]
        L2["Level 2\n특정 처장에게 위임\n(명확한 부서 명시)"]
        L3["Level 3\n처장 자율 선택\n(spawn_agent 활용)"]
        L4["Level 4\n다부서 복합\n(우선순위 정렬 후 순차)"]
    end

    subgraph DELEGATION["👔 처장 위임 + 독자분석"]
        direction TB
        MGR_SOLO["처장 독자분석 시작\n(ask_ai 호출)"]
        SPAWN["전문가 N명 동시 호출\n(병렬 실행)"]
        MGR_SOLO -.->|"동시 진행"| SPAWN
    end

    subgraph SPECIALISTS["👨‍💼 전문가 병렬 분석"]
        direction LR
        SP1["전문가 1\n(도구 호출 포함)"]
        SP2["전문가 2\n(도구 호출 포함)"]
        SP3["전문가 3\n(도구 호출 포함)"]
        SP4["전문가 4\n(도구 호출 포함)"]
    end

    subgraph TOOLS["🔧 도구 실행 (ReAct 루프)"]
        T1["뉴스 검색\n(naver_news)"]
        T2["주가 조회\n(kr_stock / us_stock)"]
        T3["웹 검색\n(real_web_search)"]
        T4["노션 저장\n(notion_api)"]
        TX["... 89개 도구"]
    end

    subgraph SYNTHESIS["📋 처장 종합"]
        GATHER["처장 독자분석 결과\n+ 전문가 N개 결과\n전부 모음"]
        REPORT["최종 보고서 작성\n(처장 판단 + 근거)"]
        QA["검수 보좌관\n품질 검증"]
    end

    subgraph OUTPUT["📤 출력 채널"]
        WEB_OUT["웹 화면\n(사령관실/작전일지)"]
        TELEGRAM_OUT["텔레그램 알림"]
        ARCHIVE_OUT["기밀문서 저장\n(자동)"]
        NOTION_OUT["노션 기록\n(자동)"]
    end

    INPUT --> ENTRY
    WEB --> ROUTING
    TELEGRAM --> ROUTING
    SCHEDULE --> ROUTING
    WORKFLOW --> ROUTING

    ROUTING --> L1
    ROUTING --> L2
    ROUTING --> L3
    ROUTING --> L4

    L1 -->|"직접 답변"| OUTPUT
    L2 --> DELEGATION
    L3 --> DELEGATION
    L4 --> DELEGATION

    DELEGATION --> MGR_SOLO
    DELEGATION --> SPAWN
    SPAWN --> SPECIALISTS

    SP1 --> TOOLS
    SP2 --> TOOLS
    SP3 --> TOOLS
    SP4 --> TOOLS

    TOOLS --> SYNTHESIS
    MGR_SOLO --> SYNTHESIS
    SPECIALISTS --> SYNTHESIS

    GATHER --> REPORT
    REPORT --> QA
    QA -->|"통과"| OUTPUT
    QA -->|"반려 + 재작업"| DELEGATION

    style INPUT fill:#fbbf24,stroke:#d97706,color:#000
    style DELEGATION fill:#ddd6fe,stroke:#7c3aed
    style SPECIALISTS fill:#d1fae5,stroke:#059669
    style QA fill:#fee2e2,stroke:#dc2626,color:#000
    style OUTPUT fill:#dbeafe,stroke:#2563eb
```

## Level 분류 기준

| Level | 조건 | 예시 |
|-------|------|------|
| Level 1 | 간단한 정보 조회, 일정 확인 | "오늘 스케줄 알려줘" |
| Level 2 | 특정 부서 명시 | "@CIO 시황 분석해줘" |
| Level 3 | 부서 미지정, 복잡한 판단 필요 | "NVDA 지금 살까?" |
| Level 4 | 여러 부서 동시 필요 | "사업계획 + 법적검토 + 마케팅 전략 세워줘" |

## 핵심: "처장 = 5번째 분석가" 원칙

> 처장은 전문가 결과를 **취합만** 하지 않고, **본인도 독자 분석**을 병렬로 수행합니다.
> 이렇게 하면 처장이 전문가에게 끌려가지 않고 독립적인 판단을 내릴 수 있습니다.
