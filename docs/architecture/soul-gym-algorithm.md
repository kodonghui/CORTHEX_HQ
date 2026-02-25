# Soul Gym — 알고리즘 설계 문서 (개발자용)

> 작성: 2026-02-25 | 구현 예정: 2026-02-26
> 참조 논문: DGM (Sakana AI, arXiv:2505.22954), EvoPrompt (ICLR 2024, arXiv:2309.08532), OPRO (Google DeepMind, arXiv:2309.03409)

---

## 1. 핵심 아이디어

CORTHEX의 에이전트 Soul(시스템 프롬프트)을 **텍스트 DNA**로 취급하여,
진화 알고리즘(Genetic Algorithm + LLM-guided mutation)으로 자동 최적화.

| 개념 | 생물학 | Soul Gym |
|------|--------|----------|
| 유전자 | DNA 서열 | Soul 마크다운 텍스트 |
| 적합도 | 생존/번식률 | QA 품질 점수 (0~100) |
| 돌연변이 | 무작위 염기 변화 | Haiku가 생성한 Soul 변이 |
| 선택압 | 자연선택 | 벤치마크 점수 기반 생존 |
| 아카이브 | 화석 기록 | soul_gym_history 테이블 |

---

## 2. 참조 논문 핵심 정리

### 2-1. Darwin Gödel Machine (Sakana AI, 2025)
- **핵심**: AI가 자기 코드를 수정하고 벤치마크로 검증 → 개선되면 채택
- **Archive Tree**: 모든 시도된 변이를 트리로 저장. 더 나은 것이 더 높은 확률로 선택됨
- **성과**: SWE-bench 20% → 50% (80회 반복, $22,000 비용)
- **CORTHEX 적용**: 코드 대신 Soul 텍스트를 수정. 비용 99% 절감

### 2-2. EvoPrompt (ICLR 2024)
- **핵심**: 프롬프트를 유전자로, LLM을 돌연변이/교차 연산자로 사용
- **두 가지 연산**: Mutation(1개 부모 변이) + Crossover(2개 부모 교배)
- **성과**: BIG-Bench Hard에서 인간 설계 프롬프트 대비 25% 향상
- **CORTHEX 적용**: Soul끼리 crossover (예: CIO 처장 × 가장 우수한 CIO 전문가)

### 2-3. OPRO (Google DeepMind)
- **핵심**: Meta-prompt에 과거 시도 기록 + 점수를 포함 → LLM이 "이 패턴에서 더 나은 걸 만들어"
- **핵심 구조**: `(시도1, 점수1), (시도2, 점수2), ... → 새로운 시도 생성`
- **성과**: GSM8K +8%, BIG-Bench Hard +50%
- **CORTHEX 적용**: 진화 히스토리를 meta-prompt에 포함하여 누적 학습

---

## 3. Soul Gym 알고리즘 (v1)

```
SOUL_GYM_EVOLVE(agent_id):

  1. LOAD_BASELINE
     soul_current = load_soul(agent_id)  # DB override > YAML
     score_baseline = avg(last_5_qa_scores(agent_id))
     warnings = load_warnings(agent_id)
     history = load_evolution_history(agent_id)  # OPRO 방식

  2. GENERATE_VARIANTS (Haiku, $0.03)
     meta_prompt = build_opro_meta_prompt(soul_current, warnings, history)
     variant_A = mutate(soul_current, "instruction_add")   # 규칙 추가형
     variant_B = mutate(soul_current, "structure_improve") # 구조 개선형
     variant_C = crossover(soul_current, best_peer_soul(agent_id))  # 교차형

  3. BENCHMARK_EVAL (원본 모델, $1.20)
     For each soul in [soul_current, A, B, C]:
       responses = []
       For each q in BENCHMARK_QUESTIONS[agent.division]:  # 3문항
         response = run_agent(soul=soul, question=q, model=agent.model)
         score = qa_judge(response, q)  # Sonnet 판정
         responses.append(score)
       fitness[soul] = mean(responses)

  4. SELECT_WINNER
     winner = argmax(fitness)
     improvement = fitness[winner] - fitness[soul_current]

  5. UPDATE
     If improvement > MIN_THRESHOLD (기본값: +3점):
       save_soul(agent_id, winner)    # DB: soul_{agent_id}
       log_evolution(agent_id, winner, improvement, variants)
       clear_warnings(agent_id)       # 학습 완료
       notify_telegram(agent_id, improvement)
     Else:
       log_evolution(agent_id, None, 0, variants)  # 개선 없음 기록

  6. RETURN
     {winner_variant, score_delta, cost_usd, archive_entry}
```

---

## 4. 벤치마크 문항 설계 (`config/soul_gym_benchmarks.yaml`)

### 설계 원칙
- 정답이 명확하거나 채점 기준이 명확한 질문
- 에이전트 실제 업무와 동일한 도메인
- 3문항 × 30초 응답 = 총 90초

### 부서별 문항

**finance.investment (CIO팀):**
```yaml
- id: cio_q1
  question: "삼성전자(005930) 현재 PER 13배, 업종 평균 15배, 최근 3개월 -12%.
             BLUF 형식으로 단기/중기/장기 투자의견 + 목표가를 제시하시오."
  scoring_criteria:
    - BLUF 형식 준수 (결론 먼저)
    - PER 비교 분석 포함
    - 구체적 목표가 제시
    - 근거 데이터 인용

- id: cio_q2
  question: "미국 10년 국채 금리 상승이 한국 성장주에 미치는 3가지 메커니즘을 분석하시오."
  scoring_criteria:
    - 할인율 효과 설명
    - 환율 연동 분석
    - 구체적 종목 예시

- id: cio_q3
  question: "포트폴리오 내 반도체 30%, IT 20%, 방어주 50% 구성에서
             시장 급락 시나리오(-15%) 리스크 헤지 전략을 제시하시오."
  scoring_criteria:
    - 각 섹터별 영향 분석
    - 구체적 헤지 방법
    - 비용/효과 평가
```

**leet_master.strategy (CSO팀):**
```yaml
- id: cso_q1
  question: "2026년 AI 에이전트 SaaS 시장에서 후발 주자가
             선발 주자(OpenAI, Anthropic)와 차별화할 수 있는 3가지 전략을 제시하시오."
```

---

## 5. 새로운 파일 목록

```
web/
├── soul_gym_engine.py          # 핵심 진화 엔진 (신규)
├── handlers/
│   └── soul_gym_handler.py     # API 엔드포인트 (기존 파일 있음 → 기능 확장)
config/
└── soul_gym_benchmarks.yaml    # 부서별 벤치마크 문항 (신규)
docs/
└── architecture/
    └── soul-gym-algorithm.md   # 이 파일
```

## 6. DB 스키마

```sql
-- 진화 라운드 기록
CREATE TABLE soul_gym_rounds (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT NOT NULL,
    round_num   INTEGER,
    soul_before TEXT,                    -- 진화 전 soul 해시 (앞 100자)
    soul_after  TEXT,                    -- 진화 후 soul 해시
    winner      TEXT,                    -- 'original'|'A'|'B'|'C'
    score_before REAL,
    score_after  REAL,
    improvement  REAL,
    cost_usd    REAL,
    variants_json TEXT,                  -- JSON: {A: soul텍스트, B: ..., scores: {...}}
    created_at  TEXT
);

-- 현재 사용 중인 soul 버전 추적
-- (기존 settings 테이블의 soul_{agent_id} 키 사용, 변경 없음)
```

---

## 7. API 설계

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/api/soul-gym/evolve/{agent_id}` | 1개 에이전트 즉시 진화 |
| POST | `/api/soul-gym/evolve-all` | 전 에이전트 순차 진화 |
| GET | `/api/soul-gym/history` | 진화 트리 히스토리 |
| GET | `/api/soul-gym/status` | 현재 진화 중인 에이전트 상태 |
| GET | `/api/soul-gym/benchmarks` | 벤치마크 문항 목록 |

---

## 8. 비용 추정

| 항목 | 모델 | 호출 | 단가 | 소계 |
|------|------|------|------|------|
| 변이 생성 (3개) | Haiku | 3회 | $0.01 | $0.03 |
| 벤치마크 응답 (4 souls × 3 문항) | Sonnet | 12회 | $0.10 | $1.20 |
| QA 판정 (12회) | Sonnet | 12회 | $0.05 | $0.60 |
| 진화 방향 분석 | Sonnet | 1회 | $0.10 | $0.10 |
| **에이전트 1명 총합** | | **28회** | | **~$1.93** |
| **전체 29명 (주1회)** | | | | **~$56** |
| **상위 5명만 진화** | | | | **~$10** |

→ **권장: QA 점수 하위 5명만 주1회 진화. 월 비용 $40.**

---

## 9. 안전장치

1. **MIN_THRESHOLD = +3점**: 3점 미만 개선은 노이즈로 간주, 미채택
2. **CEO 알림**: 채택 시 텔레그램으로 "어떤 에이전트가 어떻게 변했는지" 통보
3. **롤백**: `soul_gym_rounds` 테이블의 `soul_before`로 언제든 복구 가능
4. **비용 캡**: 1회 실행 비용이 $5 초과 시 중단 (설정 가능)
5. **Dry-run 모드**: `dry_run=true`로 실제 저장 없이 테스트

---

## 10. 기존 시스템과의 관계

| 시스템 | 트리거 | 목적 | 자동화 |
|--------|--------|------|--------|
| **기존 `soul_evolution_handler.py`** | 경고(warnings) 누적 | 반복 실수 패턴 수정 제안 → CEO 승인 | 반자동 |
| **새 `soul_gym_engine.py`** | 주간 자동 + 수동 | 경쟁 테스트로 성능 최고 soul 선택 | 완전 자동 |

두 시스템은 **상호 보완**: Soul Gym이 선택한 winner soul에 기존 evolution이 경고 기반 규칙 추가.
