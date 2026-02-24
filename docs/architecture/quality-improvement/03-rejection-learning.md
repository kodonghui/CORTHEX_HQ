# 03. 반려 → 학습 → 재작업 사이클

> 비유: **시험지에 빨간펜 코멘트 → 학생이 다음 시험 전에 복습.**
> 반려 교훈이 `warnings`에 저장되면, 이 전문가가 **다음 분석에서도** 자동 주입됨.

## 다이어그램

```mermaid
flowchart LR
    subgraph QA["품질검수 (CIO)"]
        Q1[전문가 보고서 수신] --> Q2[quality_rules.yaml<br/>기준으로 채점]
        Q2 --> Q3{합격?<br/>평균 ≥ 3.0}
    end

    subgraph REJECT["반려 처리"]
        Q3 -->|No| R1["반려사유 추출<br/>'Q4 1점: 진입가 미명시'"]
        R1 --> R2[교신로그 기록<br/>'❌ 종목분석 반려']
        R1 --> R3[기밀문서 저장<br/>'cio보고서3_반려사유']
        R1 --> R4["🧠 학습 저장<br/>warnings 카테고리에<br/>반려 교훈 기록"]
    end

    subgraph REWORK["재작업"]
        R2 & R3 & R4 --> RW1["재작업 프롬프트 구성"]
        RW1 --> RW2["[이전 보고서 원문]<br/>+ [반려 사유]<br/>+ [부분 수정 지시]"]
        RW2 --> RW3["[에이전트 기억 자동 주입]<br/>주의: Q4 반려 경험"]
        RW3 --> RW4[전문가 재작업 실행]
        RW4 --> RW5["재작업 보고서<br/>기밀문서 저장 (v2)"]
        RW5 --> RW6[활동로그 기록<br/>'🔄 재작업 제출']
    end

    subgraph RECHECK["재검수"]
        RW6 --> RC1[QA 재채점]
        RC1 --> RC2{합격?}
        RC2 -->|Yes| PASS[✅ 합격<br/>종합 단계로]
        RC2 -->|No| R1
    end

    Q3 -->|Yes| PASS

    style QA fill:#1a1a2e,color:#e0e0e0
    style REJECT fill:#dc3545,color:white
    style REWORK fill:#ffc107,color:black
    style RECHECK fill:#0f3460,color:#e0e0e0
    style PASS fill:#28a745,color:white
```

## 학습의 핵심

반려 교훈이 `warnings`에 저장되면, 이 전문가가 **다음 분석에서도** 자동 주입됨.

### 향후 확대
같은 메모리 시스템이 모든 29명 에이전트에 적용 가능.
