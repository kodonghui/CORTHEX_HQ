# CORTHEX 비전 + 리트마스터 컨텍스트

> **이 문서는 Claude가 매 세션마다 참조해야 하는 핵심 문서입니다.**
> 대표님이 왜 CORTHEX를 만들었는지, 리트마스터가 무엇인지, 전체 사업 방향이 어디인지 이해하기 위해 필수 열람하세요.

---

## 1. CORTHEX가 뭐야?

CORTHEX = **대뇌피질(Cortex)** + **핵심(Hex)**

고동희 대표님이 만든 **AI 멀티에이전트 조직 시스템**입니다.
사람이 아니라 **AI가 직원인 회사** — 비서실, 법무처, CTO부서, 재무부 등 실제 조직 구조에 AI 에이전트를 배치하고, 각각에게 역할/성격/도구를 부여합니다.

**핵심 철학**: "진짜 직원이었으면 좋겠다" — 단순 챗봇이 아니라, 스스로 판단하고 도구를 쓰고 보고하는 에이전트

---

## 2. 리트마스터 (LEET MASTER)

### 개요

| 항목 | 내용 |
|------|------|
| **프로젝트명** | LEET MASTER — 추리논증 학습 플랫폼 |
| **GitHub** | https://github.com/kodonghui/leet-master |
| **프로덕션** | https://leet-master.pages.dev |
| **목적** | LEET(법학적성시험) 추리논증 문제 풀이 + AI 해설/피드백 |
| **대상** | 법학전문대학원 입학 준비 수험생 |
| **문제 수** | 715문제 (2009년 예비시험~2026년) |

### 기술 스택

| 영역 | 기술 |
|------|------|
| Backend | Hono (TypeScript) on Cloudflare Workers |
| Frontend | Vanilla JS + TailwindCSS + FontAwesome (CDN) |
| Database | Cloudflare D1 (SQLite), 24개 테이블, 19개 마이그레이션 |
| AI | OpenAI (GPT-5.2), Claude (Opus 4.6), Gemini (확장 예정) |
| 배포 | Cloudflare Pages |
| Cron | Cloudflare Workers (5분 주기 Batch 처리) |
| 인증 | JWT Bearer 토큰 |
| 노션 | 양방향 Sync (Notion ↔ GitHub) |

### AI 피드백 3단계 시스템

리트마스터의 핵심 기능은 **수준별 AI 피드백**입니다.

| 수준 | 표시명 | 기본 모델 | 최대 글자 | 방식 |
|------|--------|-----------|----------|------|
| simple | 간단 피드백 | GPT-4o-mini | 1,200자 | 실시간 API |
| detailed | 상세 피드백 | GPT-4o | 2,500자 | 실시간 API |
| deep | 심층 분석 | GPT-5 / Claude Opus 4.6 | 4,000자 | **Batch API** (30% 할인) |

**피드백 생성 흐름:**
1. 수험생이 문제를 풀고 답안 제출
2. 피드백 수준 선택 (간단/상세/심층)
3. 프롬프트 템플릿에 문제 + 학생 답안 + AI 통합해설 주입
4. 해당 수준의 AI 모델로 호출
5. 크레딧 차감 (토큰수 / 10 × 마진율 2.0)

**프롬프트 출력 구조:**
I. 결과 → II. 진단 → III. 핵심 → IV. 함정 → V. 학습 포인트 → VI. 올바른 접근법

### Batch API 시스템

심층 분석은 비동기 Batch API로 처리됩니다.

- **OpenAI Batch API** + **Anthropic Message Batches API** 모두 지원
- 모델명에 따라 자동 분기 (`claude-` → Anthropic, 그 외 → OpenAI)
- Cron Worker가 5분 주기로 Batch 상태 확인
- 크레딧: 사전 홀드 → 성공 시 실제 사용량 차감 + 차액 환불, 실패 시 전액 환불

### 크레딧 시스템 (수익 모델)

| 상품 | 크레딧 | 가격 | 보너스 |
|------|--------|------|--------|
| 스타터 | 1,000 | 1,000원 | — |
| 베이직 | 5,000 | 4,500원 | +500 |
| 스탠다드 | 10,000 | 8,000원 | +2,000 |
| 프리미엄 | 30,000 | 20,000원 | +10,000 |

- AI 해설 잠금해제: 100 크레딧
- 결제: 계좌이체(기업은행) → 관리자 수동 확인 → 크레딧 지급

### PJ1 — 멀티에이전트 경영회의

리트마스터 저장소에 포함된 별도 프로젝트(`PJ1_biz_debates/`)입니다.

| 역할 | AI 모델 | 용도 |
|------|---------|------|
| CEO (김대표) | Claude Opus 4.6 | 최종 의사결정, 리스크 평가 |
| CTO (박기술) | Gemini 3 Pro Preview | 기술 판단, 개발 공수 산정 |
| CMO (이마케) | GPT-5.2 Pro | 마케팅 전략, CAC/LTV 산출 |

- 7라운드 34메시지 구조 (PDCA 사이클)
- 1회 비용: $35~45, 소요 시간: 2~2.5시간

### 현재 상태 (2026-02 기준)

- **구현 완료**: 문제 풀이, AI 피드백 3단계, Batch API, Cron, 크레딧 과금, 관리자 대시보드, Notion 연동
- **개발 중단 중**: CTO부서 5명 동면 모드 (리트마스터 재개 시 복귀)
- **사업화 준비**: 예비창업패키지 심사 준비, 설문조사 설계, 저작권 문의, 특허 비용 파악

---

## 3. CORTHEX ↔ 리트마스터 연결

CORTHEX HQ는 **본사**, 리트마스터는 **첫 번째 사업**입니다.

```
CORTHEX HQ (AI 조직)
  ├── 비서실: 일정/뉴스/보고
  ├── 법무처: 한국법 자문
  ├── 재무부: 투자/기업분석
  ├── 출판국: SNS/콘텐츠
  └── CTO부서 (= LEET MASTER 팀)
       ├── CTO: 기술 총괄
       ├── 프론트엔드 개발자
       ├── 백엔드 개발자
       ├── 인프라 엔지니어
       └── AI 모델 전문가
```

CTO부서는 리트마스터를 개발하던 팀이었고, 개발 중단 중이라 현재 동면(Flash low) 모드입니다.

---

## 4. 대표님의 비전

대표님이 직접 밝힌 장기 목표:

1. **CORTHEX = AI가 직원인 회사** — 에이전트가 스스로 도구를 쓰고, 크롤링하고, 보고서 작성하고, 엑셀에 값을 넣는 진짜 직원
2. **리트마스터 = 첫 번째 수익 사업** — 수험생 대상 AI 학습 플랫폼, 크레딧 과금
3. **데이터 파이프라인** — 서로연/오르비/디씨 크롤링 → 수험생 수요 분석 → 콘텐츠 자동 생성
4. **SNS 자동화** — 인스타그램/유튜브 쇼츠 자동 게시
5. **Defining Age** — 대표님의 사업 패러다임 (자세한 내용은 `docs/defining-age.md`)

---

## 5. 리트마스터 파일 구조 요약

```
leet-master/
├── src/
│   ├── index.tsx                   # Hono 앱 (라우터 + JWT)
│   ├── routes/
│   │   ├── auth.ts                 # 인증
│   │   ├── problems.ts             # 문제 조회
│   │   ├── answers.ts              # 답안 제출
│   │   ├── feedback.ts             # AI 피드백 (3단계)
│   │   ├── batch.ts                # Batch API (심층분석)
│   │   ├── ai-analysis.ts          # AI 해설 잠금해제/북마크
│   │   ├── stats.ts                # 학습 통계
│   │   ├── payments.ts             # 결제
│   │   ├── sync.ts                 # Notion 양방향 동기화
│   │   └── admin.ts                # 관리자
│   ├── lib/
│   │   ├── prompts.ts              # 프롬프트 템플릿 (핵심!)
│   │   ├── pricing.ts              # 모델별 가격/크레딧
│   │   ├── ai-providers.ts         # AI 제공자 (OpenAI/Claude/Gemini)
│   │   └── services/sync-service.ts
│   └── types/index.ts
├── public/static/app.js            # 프론트엔드 (7500줄+)
├── migrations/ (0001~0019)         # D1 마이그레이션
├── PJ1_biz_debates/                # 멀티에이전트 경영회의
└── docs/                           # 문서
```

---

## 6. 기억해야 할 것

- 리트마스터는 **Cloudflare** 생태계 (Workers + D1 + Pages), CORTHEX HQ는 **Oracle Cloud** (Ubuntu + SQLite + nginx)
- 리트마스터 AI는 **3단계 피드백** 구조, CORTHEX HQ AI는 **에이전트별 도구 호출** 구조
- 대표님은 법학전공자 → 리트마스터 = 본인의 전문 분야에서 출발한 사업
- 해설 파이프라인(1차 가공 → 2차 통합 → 3차 루브릭)은 리트마스터 GitHub에는 코드가 없음 → 별도 위치에서 관리되는 것으로 추정
- Git 워크플로우: 두 프로젝트 모두 `claude/` 브랜치 + `[완료]` 자동 머지 동일
