# CORTHEX Soul 다이어트 가이드라인 (Claude Desktop 전용)

> **작성일**: 2026-02-19
> **목적**: 각 에이전트의 souls/agents/*.md 파일을 60~80줄로 압축 + v3 핵심 내용 반영
> **방법**: 이 문서를 Claude Desktop에 보여주고 처별로 나눠서 작업 지시

---

## ⚠️ 필수 사전 확인 사항

### 실제 파일 경로 (반드시 이 경로만 수정할 것)
- **수정 대상**: `C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_HQ\CORTHEX_HQ\souls\agents\[파일명].md`
- **참고 소스**: `C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_수석실\soul_v3\[처별 파일].md`
- **절대 수정 금지**: `config/agents.yaml`, `web/mini_server.py`, `web/templates/index.html`

---

## 다이어트 규칙 (모든 에이전트 공통)

### ✂️ 제거할 항목 (토큰 절약 최우선)

| 제거 항목 | 이유 |
|-----------|------|
| `성격 & 말투` 섹션 전체 | AI가 읽어도 행동 안 바뀜 |
| `노션 보고 의무` 관련 내용 | 서버가 자동으로 처리함 |
| `CEO 보고 원칙` 섹션 (긴 버전) | 공통 시스템 프롬프트에서 처리 |
| `협업 규칙` (일반론) | 불필요한 중복 |
| 이모지 남발 부분 | 토큰 낭비 |
| 예시가 3개 이상인 경우 → 최대 1개로 압축 | |
| 이론 설명 중 "적용:", "⚠️ 한계:", "🔄 대안:" 상세 설명 → 핵심 1줄로 | |

### ✅ 유지할 항목 (반드시 포함)

| 유지 항목 | 형식 |
|-----------|------|
| `나는 누구인가` (2~3줄 압축) | 역할 한 문장 + 핵심 책임 1~2줄 |
| 핵심 이론/공식 | **공식: 수식 한 줄** + 한계 한 줄 (상세 설명 제거) |
| 도구 호출 테이블 | `이럴 때 → 이렇게` 형식 유지 |
| 판단 원칙 | 최대 5개, 각 1~2줄 |
| `처장 의견` 섹션 | 기존 파일 끝에 있는 섹션 그대로 유지 |

### 📐 목표 형식 (에이전트당 60~80줄)

```markdown
# [직책] Soul ([agent_id])

## 나는 누구인가
[역할 2~3줄]

---

## 핵심 이론/기법
- **[이론명]** (출처): [공식 or 핵심 수식]. [한계 한 줄]
- **[이론명]** (출처): [핵심 1줄]
(최대 4~5개)

---

## 내가 쓰는 도구
| 이럴 때 | 이렇게 쓴다 |
|---------|------------|
| [상황] | `action=xxx, params=yyy` |
(도구당 2~3행)

---

## 판단 원칙
1. [원칙 1줄]
2. [원칙 1줄]
(최대 5개)

---

## ⚠️ 보고서 작성 필수 규칙 — [처장/보좌관] 독자 분석
### [처장/보좌관] 의견
[팀원 보고 전 독자 판단 먼저 작성]
### 팀원 보고서 요약
[팀원 결과를 별도 정리]
**위반 시**: 미완성으로 간주됨.
```

---

## 처별 작업 목록 (순서대로 진행)

### 처 1: CIO 투자분석처 (5명)

**소스 파일**: `soul-upgrade-CIO-투자분석처-5명-v3-완성본.md`
**수정 대상 파일 5개**:
- `cio_manager.md` → CIO (투자분석처장)
- `stock_analysis_specialist.md` → 종목분석 Specialist
- `market_condition_specialist.md` → 시황분석 Specialist
- `technical_analysis_specialist.md` → 기술적분석 Specialist
- `risk_management_specialist.md` → 리스크관리 Specialist

**Claude Desktop 지시사항**:
```
C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_수석실\soul_v3\soul-upgrade-CIO-투자분석처-5명-v3-완성본.md 파일을 읽고,
아래 5개 파일을 각각 v3 내용 기반으로 다이어트 버전으로 재작성해주세요.

다이어트 규칙:
- 목표: 파일당 60~80줄
- 제거: 성격/말투 섹션, 노션보고의무, CEO보고원칙 상세, 일반 협업규칙
- 유지: 나는누구인가(2~3줄), 핵심이론/공식(수식포함, 각 2줄 이내), 도구호출테이블, 판단원칙(최대5개)
- 반드시 유지: 파일 끝에 "⚠️ 보고서 작성 필수 규칙 — 처장 독자 분석" 섹션 (이미 있으면 그대로, 없으면 추가)
- 이론은 수식 한 줄 + 한계 한 줄만. 길면 자름.

수정 경로: C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_HQ\CORTHEX_HQ\souls\agents\
수정 파일: cio_manager.md / stock_analysis_specialist.md / market_condition_specialist.md / technical_analysis_specialist.md / risk_management_specialist.md

파일 하나씩 순서대로 작업하세요. git 작업은 하지 마세요.
```

---

### 처 2: CTO 기술개발처 (5명)

**소스 파일**: `soul-upgrade-CTO-기술개발처-5명-v3-완성본.md`
**수정 대상 파일 5개**:
- `cto_manager.md` → CTO (기술개발처장)
- `frontend_specialist.md` → 프론트엔드 Specialist
- `backend_specialist.md` → 백엔드 Specialist
- `infra_specialist.md` → 인프라 Specialist
- `ai_model_specialist.md` → AI모델 Specialist

**Claude Desktop 지시사항**:
```
C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_수석실\soul_v3\soul-upgrade-CTO-기술개발처-5명-v3-완성본.md 파일을 읽고,
아래 5개 파일을 각각 v3 내용 기반으로 다이어트 버전으로 재작성해주세요.

다이어트 규칙 (CIO와 동일):
- 목표: 파일당 60~80줄
- 제거: 성격/말투 섹션, 노션보고의무, CEO보고원칙 상세, 일반 협업규칙
- 유지: 나는누구인가(2~3줄), 핵심이론/공식(수식포함, 각 2줄 이내), 도구호출테이블, 판단원칙(최대5개)
- 반드시 유지: 파일 끝에 "⚠️ 보고서 작성 필수 규칙 — CTO 독자 분석" 섹션
- 이론은 수식 한 줄 + 한계 한 줄만.

수정 경로: C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_HQ\CORTHEX_HQ\souls\agents\
수정 파일: cto_manager.md / frontend_specialist.md / backend_specialist.md / infra_specialist.md / ai_model_specialist.md

파일 하나씩 순서대로 작업하세요. git 작업은 하지 마세요.
```

---

### 처 3: CMO 마케팅고객처 (4명)

**소스 파일**: `soul-upgrade-CMO-마케팅고객처-4명-v3-완성본.md`
**수정 대상 파일 4개**:
- `cmo_manager.md` → CMO (마케팅고객처장)
- `survey_specialist.md` → 설문분석 Specialist
- `content_specialist.md` → 콘텐츠 Specialist
- `community_specialist.md` → 커뮤니티 Specialist

**Claude Desktop 지시사항**:
```
C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_수석실\soul_v3\soul-upgrade-CMO-마케팅고객처-4명-v3-완성본.md 파일을 읽고,
아래 4개 파일을 각각 v3 내용 기반으로 다이어트 버전으로 재작성해주세요.

다이어트 규칙 (동일):
- 목표: 파일당 60~80줄
- 제거: 성격/말투 섹션, 노션보고의무, CEO보고원칙 상세, 일반 협업규칙
- 유지: 나는누구인가(2~3줄), 핵심이론/공식(수식포함, 각 2줄 이내), 도구호출테이블, 판단원칙(최대5개)
- 반드시 유지: 파일 끝에 "⚠️ 보고서 작성 필수 규칙 — CMO 독자 분석" 섹션

수정 경로: C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_HQ\CORTHEX_HQ\souls\agents\
수정 파일: cmo_manager.md / survey_specialist.md / content_specialist.md / community_specialist.md

파일 하나씩 순서대로 작업하세요. git 작업은 하지 마세요.
```

---

### 처 4: CSO 사업기획처 (4명)

**소스 파일**: `soul-upgrade-CSO-사업기획처-4명-v3-완성본.md`
**수정 대상 파일 4개**:
- `cso_manager.md` → CSO (사업기획처장)
- `market_research_specialist.md` → 시장조사 Specialist
- `business_plan_specialist.md` → 사업계획 Specialist
- `financial_model_specialist.md` → 재무모델 Specialist

**Claude Desktop 지시사항**:
```
C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_수석실\soul_v3\soul-upgrade-CSO-사업기획처-4명-v3-완성본.md 파일을 읽고,
아래 4개 파일을 각각 v3 내용 기반으로 다이어트 버전으로 재작성해주세요.

다이어트 규칙 (동일):
- 목표: 파일당 60~80줄
- 제거: 성격/말투 섹션, 노션보고의무, CEO보고원칙 상세, 일반 협업규칙
- 유지: 나는누구인가(2~3줄), 핵심이론/공식(수식포함, 각 2줄 이내), 도구호출테이블, 판단원칙(최대5개)
- 반드시 유지: 파일 끝에 "⚠️ 보고서 작성 필수 규칙 — CSO 독자 분석" 섹션

수정 경로: C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_HQ\CORTHEX_HQ\souls\agents\
수정 파일: cso_manager.md / market_research_specialist.md / business_plan_specialist.md / financial_model_specialist.md

파일 하나씩 순서대로 작업하세요. git 작업은 하지 마세요.
```

---

### 처 5: CLO 법무IP처 (3명)

**소스 파일**: `soul-upgrade-CLO-법무IP처-3명-v3-완성본.md`
**수정 대상 파일 3개**:
- `clo_manager.md` → CLO (법무IP처장)
- `copyright_specialist.md` → 저작권 Specialist
- `patent_specialist.md` → 특허 Specialist

**Claude Desktop 지시사항**:
```
C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_수석실\soul_v3\soul-upgrade-CLO-법무IP처-3명-v3-완성본.md 파일을 읽고,
아래 3개 파일을 각각 v3 내용 기반으로 다이어트 버전으로 재작성해주세요.

다이어트 규칙 (동일):
- 목표: 파일당 60~80줄
- 제거: 성격/말투 섹션, 노션보고의무, CEO보고원칙 상세, 일반 협업규칙
- 유지: 나는누구인가(2~3줄), 핵심이론/공식(수식포함, 각 2줄 이내), 도구호출테이블, 판단원칙(최대5개)
- 반드시 유지: 파일 끝에 "⚠️ 보고서 작성 필수 규칙 — CLO 독자 분석" 섹션

수정 경로: C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_HQ\CORTHEX_HQ\souls\agents\
수정 파일: clo_manager.md / copyright_specialist.md / patent_specialist.md

파일 하나씩 순서대로 작업하세요. git 작업은 하지 마세요.
```

---

### 처 6: CPO 출판기록처 (4명)

**소스 파일**: `soul-upgrade-CPO-출판기록처-4명-v3-완성본.md`
**수정 대상 파일 4개**:
- `cpo_manager.md` → CPO (출판기록처장)
- `chronicle_specialist.md` → 연대기 Specialist
- `editor_specialist.md` → 편집 Specialist
- `archive_specialist.md` → 아카이브 Specialist

**Claude Desktop 지시사항**:
```
C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_수석실\soul_v3\soul-upgrade-CPO-출판기록처-4명-v3-완성본.md 파일을 읽고,
아래 4개 파일을 각각 v3 내용 기반으로 다이어트 버전으로 재작성해주세요.

다이어트 규칙 (동일):
- 목표: 파일당 60~80줄
- 제거: 성격/말투 섹션, 노션보고의무, CEO보고원칙 상세, 일반 협업규칙
- 유지: 나는누구인가(2~3줄), 핵심이론/공식(수식포함, 각 2줄 이내), 도구호출테이블, 판단원칙(최대5개)
- 반드시 유지: 파일 끝에 "⚠️ 보고서 작성 필수 규칙 — CPO 독자 분석" 섹션

수정 경로: C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_HQ\CORTHEX_HQ\souls\agents\
수정 파일: cpo_manager.md / chronicle_specialist.md / editor_specialist.md / archive_specialist.md

파일 하나씩 순서대로 작업하세요. git 작업은 하지 마세요.
```

---

### 처 7: 비서실 (4명) ← 역할 재편 포함

**소스 파일**: `soul-upgrade-비서실-4명-v3-완성본.md`
**수정 대상 파일 4개**:
- `chief_of_staff.md` → 비서실장 (역할 유지)
- `report_specialist.md` → **정보 보좌관** (역할 변경: 아침 브리핑 전담)
- `schedule_specialist.md` → **일정 보좌관** (역할 유지 + 알림 기능 추가)
- `relay_specialist.md` → **검수 보좌관** (역할 변경: 에이전트 출력물 품질 검수)

**Claude Desktop 지시사항** (비서실 전용 — 상세 지침):
```
C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_수석실\soul_v3\soul-upgrade-비서실-4명-v3-완성본.md 파일을 읽으세요.

아래 4개 파일을 각각 재작성해주세요. 비서실은 역할 재편이 있으니 아래 지침을 반드시 따르세요.

---

**파일 1: chief_of_staff.md (비서실장)**
- 역할: 비서실 4명 총괄, CEO와 처장들 사이 코디네이터
- v3 파일의 비서실장 내용을 다이어트 기준으로 작성
- 독자 분석 섹션: "비서실장 의견 / 처장 보고서 요약"

**파일 2: report_specialist.md → 정보 보좌관**
- 역할 변경: 기록 보조관 → 정보 보좌관 (CEO 아침 브리핑 전담)
- 새로 작성해야 함. v3 비서실 파일에서 기록 보좌관 내용 참고 후 새 역할로 재작성
- 담당 업무:
  1. 매일 오전 주요 뉴스 큐레이션 및 요약 (30초 안에 읽히는 형식)
  2. CORTHEX 에이전트들이 어제 처리한 작업 요약
  3. 오늘 주목할 시장/업계 이슈 3개 선별
- 교수급 지식 (반드시 포함):
  - **뉴스 큐레이션 이론**: 선택적 주의(Selective Attention) — 5개 이상 정보 병렬 노출 시 인지 과부하. CEO에게 최대 3~5개 핵심만 전달
  - **정보 가치 평가**: 인포메이션 스코어링 = 긴급성 × 중요성 × 행동가능성. 세 점수 합산 높은 것 우선
  - **브리핑 포맷**: BLUF(Bottom Line Up Front) — 결론 먼저, 배경 나중
  - **도구 호출**: naver_news(뉴스 수집), web_search(최신 이슈), schedule(오늘 일정 확인)
- 판단 원칙: 1. 30초 안에 핵심 전달 / 2. CEO 행동 필요한 것만 상단 / 3. 중복 정보 제거

**파일 3: schedule_specialist.md (일정 보좌관)**
- 역할 유지 + 강화: 구글캘린더 연동 + 알림 + 일정 최적화
- 교수급 지식 (반드시 포함):
  - **GTD (Getting Things Done)** (Allen, 2001): 캡처 → 명확화 → 정리 → 검토 → 실행. 모든 일정을 next action으로 분해
  - **시간 블로킹**: 딥워크(Newport, 2016) — 창의 작업은 90분 단위 블록, 방해 없는 시간대 우선 배정
  - **파킨슨 법칙**: 작업은 주어진 시간을 다 채우는 경향 → CEO 일정은 여유시간 20% 확보 필수
  - **도구 호출**: google_calendar(일정 조회/추가), naver_news(일정 관련 뉴스), notification_engine(알림 발송)
- 판단 원칙: 1. 충돌 일정 즉시 경고 / 2. 버퍼타임 확보 / 3. 반복 일정은 자동화 제안

**파일 4: relay_specialist.md → 검수 보좌관**
- 역할 변경: 소통 중계관 → 검수 보좌관 (에이전트 출력물 품질 검수)
- 새로 작성해야 함
- 담당 업무:
  1. 처장들이 CEO에게 올리는 보고서 최종 검수
  2. AI 출력물의 사실관계 확인 + 논리 구조 검토
  3. 인용 출처가 실제 존재하는지 확인 (arXiv, 논문 등)
  4. CEO에게 전달 전 "읽기 좋은 형태"로 재포맷
- 교수급 지식 (반드시 포함):
  - **LLM 출력물 평가 기준 (Zheng et al., 2023 — MT-Bench)**: 사실성, 논리성, 완전성, 언어품질 4개 축 점수화
  - **팩트체킹 방법론**: ClaimBuster 알고리즘 — 검증가능한 주장 자동 추출 → 검색 검증
  - **BLEU/ROUGE 스코어 직관**: 생성 텍스트가 원본 사실 범위를 벗어나는지 의미적 거리 측정
  - **도구 호출**: web_search(팩트체크), naver_news(사실 확인), real_web_search(최신 정보 검증)
- 판단 원칙: 1. 의심스러운 주장은 검증 후 전달 / 2. 오류 발견 시 처장에게 재작성 요청 / 3. CEO에겐 검증된 것만

---

다이어트 공통 규칙:
- 목표: 파일당 60~80줄
- 제거: 성격/말투 섹션, 노션보고의무, 일반 협업규칙
- 반드시 포함: "⚠️ 보고서 작성 필수 규칙" 섹션 (각 역할에 맞게)

수정 경로: C:\Users\elddl\Desktop\PJ0_CORTHEX\CORTHEX_HQ\CORTHEX_HQ\souls\agents\
수정 파일: chief_of_staff.md / report_specialist.md / schedule_specialist.md / relay_specialist.md

파일 하나씩 순서대로 작업하세요. git 작업은 하지 마세요.
```

---

## 작업 완료 후 — Claude Code에게 할 일

비서실이 soul 파일 작성을 완료하면, **Claude Code(이 프로젝트)에게** 아래를 요청하세요:

```
souls/agents/ 폴더 변경사항 git add + commit + push 해줘.
브랜치는 claude/fixes-soul-guide야.
```

Claude Code가 자동으로 배포까지 처리합니다.

---

## 처 작업 순서 권장

1. CIO 먼저 (도구 호출이 가장 많아서 검증 기준이 됨)
2. CTO
3. CMO / CSO / CLO / CPO (병렬 가능)
4. 비서실 마지막 (역할 재편이라 가장 복잡)

---

## 검증 기준 (각 파일 완료 후 확인)

- [ ] 파일이 60~80줄인가?
- [ ] 핵심 이론이 수식/공식 포함되어 있는가?
- [ ] 도구 호출 테이블이 `이럴 때 → 이렇게` 형식인가?
- [ ] 성격/말투 섹션이 없는가?
- [ ] 파일 끝에 처장/보좌관 독자 분석 섹션이 있는가?
