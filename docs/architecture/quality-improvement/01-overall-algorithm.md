# 01. 전체 품질 개선 사이클

> 비유: **시험 → 빨간펜 → 보충수업 → 재시험**
> 투자분석처에서 시작 → 전 부서 확대 가능한 구조

## 다이어그램

```mermaid
flowchart TB
    subgraph MEASURE["① 측정 (블라인드 채점)"]
        A1[분석 1회 실행] --> A2[보고서 + 활동로그 수집]
        A2 --> A3[루브릭 기반 채점<br/>Q0~Q9 / C1~C4 / E1~E5]
        A3 --> A4[실제 시장 데이터<br/>교차검증]
    end

    subgraph ANALYZE["② 분석 (문제 발견)"]
        A4 --> B1{전문가별<br/>취약 차원?}
        B1 --> B2[Soul 문제<br/>BLUF 미지시 등]
        B1 --> B3[도구 문제<br/>pandas-ta 등]
        B1 --> B4[구조 문제<br/>스폰/반려/저장]
        B1 --> B5[효율 문제<br/>중복 호출/스폰]
    end

    subgraph IMPROVE["③ 개선 (9 Phase 실행)"]
        B2 --> C1[Phase 1: Soul/YAML]
        B3 --> C2[Phase 2~5: 서버 코드]
        B4 --> C3[Phase 3,8: 워크플로우]
        B5 --> C4[Phase 2: 스폰 필터링]
        C1 & C2 & C3 & C4 --> C5[Phase 6: 배포]
    end

    subgraph VERIFY["④ 검증 (재채점)"]
        C5 --> D1[분석 재실행]
        D1 --> D2[동일 루브릭 재채점]
        D2 --> D3{점수 향상?}
        D3 -->|Yes| D4[✅ 다음 부서 확대]
        D3 -->|No| A1
    end

    style MEASURE fill:#1a1a2e,color:#e0e0e0
    style ANALYZE fill:#16213e,color:#e0e0e0
    style IMPROVE fill:#0f3460,color:#e0e0e0
    style VERIFY fill:#533483,color:#e0e0e0
```

## 향후 전 부서 확대 시

이 사이클을 CSO/CMO/CPO/CLO에도 동일 적용.
각 부서의 `quality_rules.yaml` 섹션이 이미 존재 (법무/마케팅/전략 등).
부서별 루브릭만 추가하면 같은 **측정→분석→개선→검증** 사이클 반복 가능.
