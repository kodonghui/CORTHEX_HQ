# report_generator — 보고서 자동 생성기 도구 가이드

## 이 도구는 뭔가요?
분석 결과나 데이터를 전문적인 보고서 형태로 자동 변환하는 도구입니다.
투자 보고서, 시장 분석 보고서, 주간 종합 보고서 등 미리 준비된 템플릿(틀)에 데이터를 채워 넣고,
AI가 핵심 인사이트를 추가하여 완성된 보고서를 마크다운 또는 HTML로 생성합니다.

## 어떤 API를 쓰나요?
- **내부 템플릿 엔진** (외부 API 사용 없음)
- AI 보강에서 LLM 호출이 발생합니다
- 비용: **무료** (보고서 생성 자체는 무료, AI 보강에 약간의 API 비용)
- 필요한 키: 없음

## 사용법

### action=generate (보고서 생성)
```
action=generate, title="삼성전자 투자보고서", template="investment", format="markdown", sections={"market_overview": "시장 내용...", "stock_analysis": "분석 내용..."}
```
- 템플릿 기반 또는 자유 형식으로 보고서를 생성합니다
- `title`: 보고서 제목 (기본값: "CORTHEX 보고서")
- `template`: 사용할 템플릿 — "investment"(투자), "market"(시장분석), "weekly"(주간), "custom"(자유형식)
- `format`: 출력 형식 — "markdown"(기본) 또는 "html"
- `sections`: 각 섹션에 채울 내용 (딕셔너리 또는 JSON 문자열)
- AI가 각 섹션에 핵심 인사이트를 추가하고, 끝에 '핵심 요약'을 붙여줍니다
- 생성된 파일은 `data/reports/` 폴더에 자동 저장됩니다

**예시:**
- `action=generate, template="investment", title="삼성전자 분석"` → 투자 보고서 템플릿으로 생성
- `action=generate, template="custom", sections={"매출 분석": "...", "마케팅 성과": "..."}` → 자유 형식 보고서

### action=weekly (주간 종합 보고서 자동 생성)
```
action=weekly, week_start="2026-02-10", format="markdown"
```
- 이번 주의 활동을 요약한 주간 보고서를 자동 생성합니다
- `week_start`: 주간의 시작일 (기본값: 이번 주 월요일)
- `format`: 출력 형식 — "markdown"(기본) 또는 "html"
- `data/` 폴더의 데이터 파일들을 자동 수집하여 AI가 내용을 구성합니다
- 포함 섹션: 요약, 주요 성과, 기술 업데이트, 데이터/지표, 이슈/리스크, 다음 주 계획

**예시:**
- `action=weekly` → 이번 주 주간 보고서 자동 생성
- `action=weekly, week_start="2026-02-03", format="html"` → 특정 주의 보고서를 HTML로 생성

### action=templates (사용 가능한 템플릿 목록)
```
action=templates
```
- 사용 가능한 보고서 템플릿 목록과 각 템플릿에 포함된 섹션을 보여줍니다
- 사용 예시도 함께 제공합니다

**사용 가능한 템플릿:**
| 템플릿명 | 용도 | 포함 섹션 |
|---------|------|---------|
| investment | 투자 보고서 | 시장현황, 종목분석, 기술적분석, 리스크평가, 투자의견 |
| market | 시장 분석 보고서 | 시장개요, 경쟁환경, 시장규모(TAM/SAM/SOM), 트렌드, 기회/위협, 전략적 시사점 |
| weekly | 주간 보고서 | 요약, 성과, 기술업데이트, 지표, 이슈, 다음주계획 |
| custom | 자유 형식 | sections에 넣은 대로 자유롭게 구성 |

## 이 도구를 쓰는 에이전트들

### 1. 사업계획서 Specialist
**언제 쓰나?** 사업 분석 결과를 정형화된 보고서로 정리할 때
**어떻게 쓰나?**
- `action=generate, template="market"`으로 시장 분석 보고서 생성
- 커스텀 템플릿으로 사업계획서 형식의 보고서 생성

**실전 시나리오:**
> CEO가 "시장 분석 보고서 만들어줘" 라고 하면:
> 1. 시장조사 결과를 sections에 정리
> 2. `action=generate, template="market", title="LEET 시장 분석 보고서"` 실행
> 3. AI가 보강한 보고서를 CEO에게 전달

### 2. 재무모델링 Specialist
**언제 쓰나?** 재무 분석 결과를 투자 보고서로 정리할 때
**어떻게 쓰나?**
- `action=generate, template="investment"`로 투자 보고서 생성
- DCF, 손익분석 결과를 섹션별로 정리하여 전달

### 3. 콘텐츠 Specialist
**언제 쓰나?** 콘텐츠 성과 보고서, 마케팅 보고서 생성 시
**어떻게 쓰나?**
- `action=generate, template="custom"`으로 커스텀 콘텐츠 보고서 생성

### 4. 출판/기록처장 (CPO)
**언제 쓰나?** 주간 보고서 발행, 출판물 보고서 생성 시
**어떻게 쓰나?**
- `action=weekly`로 주간 종합 보고서 자동 생성
- 각 부서의 활동을 종합하여 CEO에게 보고

**실전 시나리오:**
> 매주 금요일 주간 보고서 작성 시:
> 1. `action=weekly` 실행
> 2. AI가 이번 주 데이터를 자동 수집하여 보고서 생성
> 3. 필요한 내용 추가/수정 후 CEO에게 전달

### 5. 회사연대기 Specialist
**언제 쓰나?** 회사 성장 기록을 정형화된 보고서로 정리할 때
**어떻게 쓰나?**
- `action=generate, template="custom"`으로 연대기 보고서 생성

### 6. 콘텐츠편집 Specialist
**언제 쓰나?** 편집 완료된 콘텐츠를 보고서 형식으로 최종 산출물 생성 시
**어떻게 쓰나?**
- `action=generate`로 편집 보고서 생성, HTML 형식으로 변환

## 주의사항
- 생성된 보고서 파일은 `data/reports/` 폴더에 저장됩니다 (배포 시 초기화될 수 있음)
- 템플릿에 없는 변수(sections 키)는 자동으로 "(데이터 없음)"으로 채워집니다
- HTML 변환은 간단한 마크다운 변환기를 사용하므로, 복잡한 마크다운 문법은 깨질 수 있습니다
- 주간 보고서(`action=weekly`)는 `data/` 폴더의 JSON 파일들을 자동 수집하는데, 데이터가 없으면 "해당 사항 없음"으로 처리됩니다
- 보고서 제목에 날짜가 자동 포함되므로, 같은 날 같은 템플릿으로 생성하면 파일이 덮어써집니다
