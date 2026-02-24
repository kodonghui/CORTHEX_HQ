# 04. CIO 7단계 워크플로우 + 산출물

> 비유: **팀장의 하루** — 먼저 혼자 판단하고, 팀원들 보고 받고, 품질 검수하고, 종합.

## 다이어그램

```mermaid
flowchart TB
    subgraph STEP1["(1) CIO 선판단"]
        S1[CIO 독자 판단<br/>전문가 지시 전] --> S1D["💾 cio보고서1<br/>'선판단_{날짜}.md'"]
    end

    subgraph STEP23["(2)+(3) 병렬 분석"]
        S2A["CIO 독자분석<br/>(도구 사용, 5번째 분석가)"]
        S2B["전문가 4명 병렬<br/>(시황/종목/기술/리스크)"]
        S2A --> S3A["💾 cio보고서2<br/>'독자분석_{날짜}.md'"]
        S2B --> S3B["💾 전문가보고서1<br/>(4건 각각 저장)"]
    end

    subgraph STEP4["(4) 품질검수"]
        S3A & S3B --> S4[CIO가 QA 실행<br/>quality_rules.yaml]
        S4 --> S4D{전원 합격?}
    end

    subgraph STEP56["(5)+(6) 반려/재작업"]
        S4D -->|No| S5["반려사유 특정<br/>+ 학습 저장"]
        S5 --> S5D["💾 cio보고서3<br/>'반려사유_{날짜}.md'"]
        S5D --> S6["전문가 재작업<br/>(이전 보고서 첨부)"]
        S6 --> S6D["💾 전문가보고서2<br/>'재작업_{날짜}.md'"]
        S6D --> S4
    end

    subgraph STEP7["(7) 최종 종합"]
        S4D -->|Yes| S7["CIO 최종 종합<br/>(보고서1+2 + 전문가 전부)"]
        S7 --> S7D["💾 cio보고서4<br/>'최종종합_{날짜}.md'"]
        S7D --> SIGNAL["📊 매매 시그널 생성"]
    end

    STEP1 --> STEP23

    style STEP1 fill:#1a1a2e,color:#e0e0e0
    style STEP23 fill:#16213e,color:#e0e0e0
    style STEP4 fill:#0f3460,color:#e0e0e0
    style STEP56 fill:#dc3545,color:white
    style STEP7 fill:#28a745,color:white
```

## 현재 vs 목표

- **현재**: (7) 최종 종합만 기밀문서 저장
- **목표**: 7단계 각각의 산출물이 별도 기밀문서로 남아야 함

## 산출물 저장 매핑

| 단계 | 저장할 문서 | 파일명 패턴 | 구현 Phase |
|------|-----------|------------|-----------|
| (1) CIO 선판단 | cio보고서1 | `cio보고서1_선판단_{날짜}.md` | Phase 8 |
| (2) 전문가 보고서 | 전문가보고서1 (각각) | `{전문가}_보고서1_{날짜}.md` | Phase 8 |
| (3) CIO 독자분석 | cio보고서2 | `cio보고서2_독자분석_{날짜}.md` | Phase 8 |
| (5) 반려사유 | cio보고서3 | `cio보고서3_반려사유_{날짜}.md` | Phase 3 |
| (6) 재작업 결과 | 전문가보고서2 | `{전문가}_보고서2_재작업_{날짜}.md` | Phase 3 |
| (7) CIO 최종 | cio보고서4 | 이미 저장됨 ✅ | - |

## 향후 확대

같은 `_manager_with_delegation()` 함수를 CSO/CMO/CPO/CLO도 사용하므로,
여기서 추가한 `save_archive()` 호출은 모든 부서에 자동 적용됨.
