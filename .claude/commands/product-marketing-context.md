---
name: product-marketing-context
version: 1.0.0
description: "사용자가 제품 마케팅 컨텍스트 문서를 만들거나 업데이트하려 할 때 사용합니다. '제품 컨텍스트', '마케팅 컨텍스트', '컨텍스트 설정', '포지셔닝' 등의 키워드에 반응하거나, 마케팅 작업 전반에서 기초 정보를 반복하고 싶지 않을 때 사용합니다. 다른 마케팅 스킬이 참조하는 `.claude/product-marketing-context.md`를 생성합니다."
---

# 제품 마케팅 컨텍스트

사용자가 제품 마케팅 컨텍스트 문서를 만들고 유지하도록 돕습니다. 다른 마케팅 스킬이 참조하는 기초적인 포지셔닝과 메시징 정보를 캡처하여, 사용자가 같은 내용을 반복하지 않도록 합니다.

문서는 `.claude/product-marketing-context.md`에 저장됩니다.

## 워크플로우

### 1단계: 기존 컨텍스트 확인

먼저 `.claude/product-marketing-context.md`가 이미 있는지 확인하세요.

**있는 경우:**
- 읽고 캡처된 내용 요약
- 업데이트하고 싶은 섹션 질문
- 해당 섹션에 대해서만 정보 수집

**없는 경우, 두 가지 옵션 제시:**

1. **코드베이스에서 자동 초안 작성** (추천): 리포의 README, 랜딩 페이지, 마케팅 카피, package.json 등을 분석하여 컨텍스트 문서 V1을 초안합니다. 사용자가 검토, 수정, 빈 부분을 채웁니다. 처음부터 시작하는 것보다 빠릅니다.

2. **처음부터 시작**: 각 섹션을 대화식으로 하나씩 진행하며 정보를 수집합니다.

대부분의 사용자는 옵션 1을 선호합니다. 초안 제시 후 질문: "수정할 부분이 있나요? 빠진 내용은?"

### 2단계: 정보 수집

**자동 초안 작성의 경우:**
1. 코드베이스 읽기: README, 랜딩 페이지, 마케팅 카피, 소개 페이지, 메타 설명, package.json, 기존 문서
2. 발견한 내용 기반으로 모든 섹션 초안 작성
3. 초안 제시하고 수정 또는 누락된 부분 확인
4. 사용자가 만족할 때까지 반복

**처음부터 시작의 경우:**
아래 각 섹션을 대화식으로 하나씩 진행합니다. 모든 질문을 한꺼번에 쏟아내지 마세요.

각 섹션에서:
1. 캡처하는 내용 간단히 설명
2. 관련 질문
3. 정확성 확인
4. 다음으로 이동

**중요:** 고객의 실제 표현을 그대로 캡처하세요. 다듬어진 설명보다 정확한 문구가 더 가치 있습니다.

---

## 캡처할 섹션

### 1. 제품 개요
- 한 줄 설명
- 하는 일 (2-3문장)
- 제품 카테고리 (어떤 "선반"에 놓이는가—고객이 어떻게 검색하는가)
- 제품 유형 (SaaS, 마켓플레이스, 이커머스, 서비스 등)
- 비즈니스 모델과 가격

### 2. 타겟 오디언스
- 타겟 기업 유형 (산업, 규모, 단계)
- 타겟 의사결정자 (역할, 부서)
- 주요 사용 사례 (해결하는 핵심 문제)
- Jobs to be done (고객이 "고용"하는 2-3가지)
- 구체적 사용 사례 또는 시나리오

### 3. 페르소나 (B2B만)
구매에 여러 이해관계자가 관여하는 경우, 각각에 대해:
- 사용자, 챔피언, 의사결정자, 재무 승인자, 기술 영향력자
- 각각이 중시하는 것, 과제, 약속하는 가치

### 4. 문제 및 페인 포인트
- 고객이 당신을 찾기 전 겪는 핵심 과제
- 현재 솔루션이 부족한 이유
- 비용 (시간, 돈, 기회)
- 감정적 긴장 (스트레스, 두려움, 의심)

### 5. 경쟁 환경
- **직접 경쟁사**: 같은 솔루션, 같은 문제 (예: Calendly vs SavvyCal)
- **2차 경쟁사**: 다른 솔루션, 같은 문제 (예: Calendly vs Superhuman 스케줄링)
- **간접 경쟁사**: 상충하는 접근법 (예: Calendly vs 개인 비서)
- 각각이 고객에게 부족한 점

### 6. 차별화
- 핵심 차별화 요소 (대안에 없는 역량)
- 어떻게 다르게 해결하는가
- 왜 그것이 더 나은가 (혜택)
- 고객이 대안 대신 당신을 선택하는 이유

### 7. 반론 및 안티페르소나
- 영업에서 듣는 상위 3가지 반론과 대응 방법
- 적합하지 않은 사람 (안티페르소나)

### 8. 전환 역학
JTBD의 4가지 힘:
- **밀기**: 현재 솔루션에서 벗어나게 하는 불만
- **끌기**: 당신에게 끌리는 요소
- **습관**: 현재 접근법에 묶이게 하는 것
- **불안**: 전환에 대한 걱정

### 9. 고객 언어
- 고객이 문제를 설명하는 방법 (원문 그대로)
- 고객이 당신의 솔루션을 설명하는 방법 (원문 그대로)
- 사용할 단어/표현
- 피할 단어/표현
- 제품 특화 용어 사전

### 10. 브랜드 보이스
- 톤 (전문적, 캐주얼, 유쾌한 등)
- 커뮤니케이션 스타일 (직접적, 대화적, 기술적)
- 브랜드 성격 (형용사 3-5개)

### 11. 증거 포인트
- 인용할 핵심 지표 또는 결과
- 주요 고객/로고
- 후기 발췌
- 핵심 가치 테마와 뒷받침 증거

### 12. 목표
- 주요 비즈니스 목표
- 핵심 전환 행동 (사람들이 하길 원하는 것)
- 현재 지표 (알고 있다면)

---

## 3단계: 문서 생성

정보 수집 후, 다음 구조로 `.claude/product-marketing-context.md`를 생성합니다:

```markdown
# Product Marketing Context

*Last updated: [date]*

## Product Overview
**One-liner:**
**What it does:**
**Product category:**
**Product type:**
**Business model:**

## Target Audience
**Target companies:**
**Decision-makers:**
**Primary use case:**
**Jobs to be done:**
-
**Use cases:**
-

## Personas
| Persona | Cares about | Challenge | Value we promise |
|---------|-------------|-----------|------------------|
| | | | |

## Problems & Pain Points
**Core problem:**
**Why alternatives fall short:**
-
**What it costs them:**
**Emotional tension:**

## Competitive Landscape
**Direct:** [Competitor] — falls short because...
**Secondary:** [Approach] — falls short because...
**Indirect:** [Alternative] — falls short because...

## Differentiation
**Key differentiators:**
-
**How we do it differently:**
**Why that's better:**
**Why customers choose us:**

## Objections
| Objection | Response |
|-----------|----------|
| | |

**Anti-persona:**

## Switching Dynamics
**Push:**
**Pull:**
**Habit:**
**Anxiety:**

## Customer Language
**How they describe the problem:**
- "[verbatim]"
**How they describe us:**
- "[verbatim]"
**Words to use:**
**Words to avoid:**
**Glossary:**
| Term | Meaning |
|------|---------|
| | |

## Brand Voice
**Tone:**
**Style:**
**Personality:**

## Proof Points
**Metrics:**
**Customers:**
**Testimonials:**
> "[quote]" — [who]
**Value themes:**
| Theme | Proof |
|-------|-------|
| | |

## Goals
**Business goal:**
**Conversion action:**
**Current metrics:**
```

---

## 4단계: 확인 및 저장

- 완성된 문서 표시
- 조정이 필요한지 확인
- `.claude/product-marketing-context.md`에 저장
- 전달: "다른 마케팅 스킬이 이제 이 컨텍스트를 자동으로 사용합니다. 업데이트하려면 언제든 `/product-marketing-context`를 실행하세요."

---

## 팁

- **구체적으로**: "어떤 문제를 해결하나요?"가 아니라 "고객을 당신에게 이끄는 #1 불만은?" 질문
- **정확한 표현 캡처**: 다듬어진 설명보다 고객의 실제 표현
- **예시 요청**: "예시를 들어주실 수 있나요?"가 더 나은 답변을 이끌어냄
- **진행하며 확인**: 각 섹션을 요약하고 넘어가기 전에 확인
- **해당 없는 것은 건너뛰기**: 모든 제품에 모든 섹션이 필요하지 않음 (예: B2C의 페르소나)
