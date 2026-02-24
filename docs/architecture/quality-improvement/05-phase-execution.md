# 05. Phase 실행 순서 + 의존관계

> 비유: **리모델링 공정표** — 배관(서버코드)이 끝나야 타일(배포) 붙일 수 있음.

## Phase 1~8 의존관계

```mermaid
flowchart LR
    subgraph PROMPT["프롬프트 레벨"]
        P1["Phase 1<br/>Soul/YAML 수정<br/>(7개 파일)"]
    end

    subgraph SERVER["서버 코드"]
        P2["Phase 2<br/>스폰 필터링<br/>(#9)"]
        P3["Phase 3<br/>반려/재작업/학습<br/>(#12,#16)"]
        P4["Phase 4<br/>검수 로그<br/>(#10)"]
        P5["Phase 5<br/>로그 소실<br/>(#1)"]
    end

    subgraph DEPLOY["배포"]
        P6["Phase 6<br/>배포 + 검증"]
    end

    subgraph POST["배포 후"]
        P7["Phase 7<br/>모의투자 활성화<br/>(#20+21)"]
        P8["Phase 8<br/>CIO 7단계<br/>(#14)"]
        P9["Phase 9<br/>차트 = Phase 1에서 완료"]
    end

    P1 --> P6
    P2 --> P6
    P3 --> P6
    P4 --> P6
    P5 --> P6
    P6 --> P7
    P6 --> P8

    P3 -.->|"반려 저장이<br/>7단계의 (5)(6)"| P8

    style PROMPT fill:#28a745,color:white
    style SERVER fill:#ffc107,color:black
    style DEPLOY fill:#dc3545,color:white
    style POST fill:#533483,color:white
```

## 전체 실행 순서 (Phase 0~13)

```mermaid
flowchart LR
    subgraph TODAY_AM["오전: 프롬프트+서버"]
        P0["Phase 0<br/>아키텍처 문서"]
        P1["Phase 1<br/>Soul/YAML"]
        P2["Phase 2<br/>스폰 필터링"]
        P3["Phase 3<br/>반려/학습"]
        P4["Phase 4<br/>검수 로그"]
        P5["Phase 5<br/>로그 소실"]
    end

    subgraph TODAY_PM["오후: 배포+후속"]
        P6["Phase 6<br/>1차 배포+검증"]
        P7["Phase 7<br/>모의투자"]
        P8["Phase 8<br/>7단계 워크플로우"]
    end

    subgraph TODAY_EVE["저녁: 확장"]
        P10["Phase 10<br/>Soul 크론 진화"]
        P11["Phase 11<br/>품질 대시보드"]
        P12["Phase 12<br/>협업 로그"]
        P13["Phase 13<br/>테스트"]
        P6B["Phase 6B<br/>2차 배포+검증"]
    end

    P0 --> P1
    P1 --> P6
    P2 --> P6
    P3 --> P6
    P4 --> P6
    P5 --> P6
    P6 --> P7
    P6 --> P8
    P8 --> P10
    P10 --> P11
    P11 --> P12
    P12 --> P13
    P13 --> P6B

    style TODAY_AM fill:#28a745,color:white
    style TODAY_PM fill:#ffc107,color:black
    style TODAY_EVE fill:#533483,color:white
```

## compact 전략

- Phase 1~5는 **병렬 작업 가능** (서로 독립)
- Phase 6(배포) 후 Phase 7~8 순차
- 대표님이 중간에 compact하셔도 각 Phase가 독립적이라 이어받기 가능

## Phase별 비유 요약

| Phase | 비유 | 한 줄 설명 |
|-------|------|-----------|
| 0 | 설계도 보관 | 아키텍처 문서 폴더 생성 + CEO 아이디어 기록 |
| 1 | 직원 매뉴얼 업데이트 | "결론 먼저, 도구 시점 표기, 차트는 코드로" |
| 2 | 다른 팀 직접 부르기 방지 | 같은 팀=직접, 다른 팀=팀장 경유, 휴직=차단 |
| 3 | 빨간펜 교정 시스템 | 틀린 부분만 고쳐라 + 교훈 저장 + 기밀문서 보관 |
| 4 | 성적표 형식 개선 | 과목마다 10장 → 1장 성적표 + 색깔 구분 |
| 5 | 서랍 크기 키우기 | 100개→5,000개 보관 + 검색 기능 |
| 6 | 건물 입주 | 서버 배포 + 검증 |
| 7 | 스위치 켜기 | 모의투자 활성화 |
| 8 | 보고서 아카이브 확대 | 7단계 각각 기밀문서 저장 |
| 10 | 주간 매뉴얼 리뷰 | 7일마다 반려 패턴 → soul 개선 제안 → 대표님 승인 |
| 11 | 학생 성적 추이 그래프 | 전문가 점수 추이 대시보드 |
| 12 | 부서 간 협조 대장 | 협업 기록 + 향후 조직 최적화 |
| 13 | 구조 검사 | 핵심 함수 자동 테스트 |
