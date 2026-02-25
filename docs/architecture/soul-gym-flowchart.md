# Soul Gym 플로우차트

> **VSCode에서 `Ctrl+Shift+V` 누르시면 그림으로 보입니다.**
> 또는 https://mermaid.live 에 붙여넣기 하세요.

---

## 1. 개발자용 — 상세 알고리즘 플로우

```mermaid
flowchart TD
    START([🕐 매주 월요일 03:00 KST\n자동 실행]) --> LOAD_SCORES

    LOAD_SCORES[📊 전체 에이전트\nQA 점수 조회] --> RANK[순위 정렬\n점수 낮은 순]
    RANK --> SELECT_TOP5[하위 5명 선택\n예: CIO전문가A 62점]

    SELECT_TOP5 --> AGENT_LOOP{다음 에이전트\n있나?}

    AGENT_LOOP -->|있음| LOAD_DATA

    subgraph PHASE1 ["📋 PHASE 1: 데이터 수집"]
        LOAD_DATA[현재 Soul 로드\nDB override > YAML]
        LOAD_DATA --> LOAD_WARN[반복 실수 로드\nwarnings 메모리]
        LOAD_WARN --> LOAD_HIST[진화 히스토리 로드\nsoul_gym_rounds 테이블]
        LOAD_HIST --> BASE_SCORE[기준 점수 계산\n최근 5회 QA 평균]
    end

    subgraph PHASE2 ["🧬 PHASE 2: 변이 생성 (Haiku, $0.03)"]
        BASE_SCORE --> META_PROMPT[OPRO 메타프롬프트 구성\n히스토리 + 경고 + 현재 Soul]
        META_PROMPT --> VAR_A[Variant A\n규칙 추가형\n예: 숫자 검증 추가]
        META_PROMPT --> VAR_B[Variant B\n구조 개선형\n예: BLUF 강화]
        META_PROMPT --> VAR_C[Variant C\n교차형 EvoPrompt\n예: 최우수 동료 Soul과 교배]
    end

    subgraph PHASE3 ["🏋️ PHASE 3: 경기장 (원본 모델, $1.20)"]
        VAR_A --> BENCH[벤치마크 3문항\n동시 실행]
        VAR_B --> BENCH
        VAR_C --> BENCH
        BASE_SCORE --> BENCH
        BENCH --> QA_JUDGE[QA 판정\nSonnet 채점\n0~100점]
        QA_JUDGE --> SCORE_A[A 점수: 78]
        QA_JUDGE --> SCORE_B[B 점수: 71]
        QA_JUDGE --> SCORE_C[C 점수: 65]
        QA_JUDGE --> SCORE_ORI[원본 점수: 62]
    end

    subgraph PHASE4 ["🏆 PHASE 4: 선택 & 저장"]
        SCORE_A --> COMPARE{최고 점수\n≥ 원본 + 3점?}
        SCORE_B --> COMPARE
        SCORE_C --> COMPARE
        SCORE_ORI --> COMPARE
        COMPARE -->|YES A승\n+16점| SAVE_WINNER[DB 저장\nsoul_agent_id = Variant A\n진화 트리 기록]
        COMPARE -->|NO 개선 없음| LOG_FAIL[실패 기록\n히스토리 저장\n다음 라운드 참고]
        SAVE_WINNER --> CLEAR_WARN[warnings 초기화\n다음 학습 준비]
        CLEAR_WARN --> TELEGRAM[📱 텔레그램 알림\n대표님에게 보고]
    end

    TELEGRAM --> AGENT_LOOP
    LOG_FAIL --> AGENT_LOOP
    AGENT_LOOP -->|없음 모두 완료| DONE([✅ 완료\n비용 보고])
```

---

## 2. 대표님용 — 비유 플로우차트

```mermaid
flowchart TD
    START([🗓️ 매주 월요일 새벽 3시\n자동 시작]) --> WHO

    WHO[📊 이번 주\n성적 꼴찌 직원 5명 선발\n예: 전문가A 62점] --> READ

    READ[📖 직원 업무 매뉴얼 읽기\n+ 이번 주 반복 실수 확인] --> MAKE

    MAKE[✍️ 매뉴얼 수정안 3개 작성\n담당: AI Haiku\n소요: 30초, 비용 3센트]

    MAKE --> TEST1[수정안 A\n규칙 추가형]
    MAKE --> TEST2[수정안 B\n구조 개선형]
    MAKE --> TEST3[수정안 C\n잘하는 동료 방식 차용]

    TEST1 --> EXAM[📝 같은 시험지 풀기\n3문제 / 전원 동일]
    TEST2 --> EXAM
    TEST3 --> EXAM
    READ --> EXAM

    EXAM --> GRADE[📋 채점\n담당: AI Sonnet\n0~100점]

    GRADE --> WINNER{최고 점수가\n원본보다 3점 이상\n높은가?}

    WINNER -->|YES\n예: 62→78 +16점| ADOPT[✅ 새 매뉴얼 채택\n직원 업무 방식 자동 업데이트]
    WINNER -->|NO\n개선 없음| KEEP[📌 현재 매뉴얼 유지\n시도 기록만 저장]

    ADOPT --> NOTIFY[📱 대표님에게\n텔레그램 보고]
    ADOPT --> RESET[반복 실수 기록 초기화\n깨끗한 상태로 다시 시작]

    NOTIFY --> NEXT[다음 직원으로]
    KEEP --> NEXT
    RESET --> NEXT

    NEXT --> DONE([✅ 5명 완료\n총 비용: 약 $10])
```

---

## 3. 전체 시스템 흐름 (기존 + 신규 통합)

```mermaid
flowchart LR
    subgraph DAILY ["📅 매일 실시간"]
        AGENT[에이전트\n분석 수행] -->|QA 불합격| WARN[반복 실수\n경고 저장]
        AGENT -->|QA 합격| SCORE_DB[QA 점수\nDB 저장]
    end

    subgraph WEEKLY_A ["📆 주 1회 일요일 — 기존 시스템"]
        WARN -->|누적| EVO_OLD[Soul Evolution\n경고 분석 → 제안]
        EVO_OLD -->|대표님 승인 필요| CEO_APPROVE{대표님\n승인?}
        CEO_APPROVE -->|YES| SOUL_UPDATE_A[Soul 업데이트]
    end

    subgraph WEEKLY_B ["📆 주 1회 월요일 — 새 시스템"]
        SCORE_DB -->|하위 5명 선발| GYM[Soul Gym\n경쟁 테스트]
        GYM -->|자동 선택| SOUL_UPDATE_B[Soul 업데이트\n자동]
        SOUL_UPDATE_B -->|결과 보고| CEO_INFO[대표님에게\n텔레그램 알림]
    end

    SOUL_UPDATE_A -->|개선된 Soul| BETTER[더 똑똑한\n에이전트]
    SOUL_UPDATE_B -->|개선된 Soul| BETTER

    BETTER --> AGENT
```

---

## 4. 비용 시각화

```mermaid
pie title "에이전트 1명 진화 비용 분해 (~$1.93)
    "벤치마크 응답 (Sonnet 12회)" : 62
    "QA 판정 (Sonnet 12회)" : 31
    "변이 생성 (Haiku 3회)" : 2
    "분석 (Sonnet 1회)" : 5
```

---

## 5. 알고리즘 핵심 논문 비유

```mermaid
mindmap
  root((Soul Gym\n핵심 아이디어))
    DGM\nDarwin Gödel Machine\nSakana AI 2025
      AI가 자기 코드 수정
      벤치마크로 검증
      좋으면 채택 나쁘면 버림
      CORTHEX 적용\nSoul 텍스트 수정으로 변환
    EvoPrompt\nICRL 2024
      프롬프트 = 유전자
      Mutation 규칙 추가
      Crossover 두 Soul 교배
      25% 성능 향상
    OPRO\nGoogle DeepMind
      과거 시도 기록을 프롬프트에 포함
      AI가 패턴 보고 개선방향 스스로 판단
      누적 학습 효과
      BIG-Bench +50%
```
