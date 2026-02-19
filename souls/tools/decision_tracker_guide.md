# decision_tracker — 의사결정 추적기 도구 가이드

## 이 도구는 뭔가요?
CEO와 임원들이 내린 중요한 결정을 기록하고 추적하는 도구입니다.
"무엇을 결정했는지, 왜 그렇게 결정했는지, 다른 선택지는 뭐가 있었는지, 결과가 어땠는지"를 체계적으로 기록합니다.
나중에 "그때 왜 그렇게 했지?"라는 질문에 바로 답할 수 있고, 축적된 의사결정 기록을 AI가 분석하여 의사결정 패턴과 개선점을 알려줍니다.

## 어떤 API를 쓰나요?
- **자체 구현** — 외부 API 없이 JSON 파일에 저장
- 비용: **무료**
- 필요한 키: 없음 (analyze 액션에서 AI 패턴 분석 시 에이전트 기본 모델 사용)
- 저장 경로: `data/decisions.json`

## 사용법

### action=record (의사결정 기록)
```
action=record, title="결정 제목", context="배경/상황", options=["선택지A", "선택지B"], chosen="선택한 것", reason="선택 이유", category="투자", impact="높음"
```
- 새로운 의사결정을 기록합니다
- title: 결정 제목 (필수)
- context: 결정 배경/상황 / options: 검토한 선택지들 / chosen: 최종 선택 / reason: 선택 이유
- category: 투자/기술/법률/마케팅/사업/일반
- impact: 높음/중간/낮음

**예시:**
- `action=record, title="AI 모델 변경", chosen="Claude Sonnet으로 교체", reason="비용 30% 절감", category="기술", impact="높음"`

### action=list (의사결정 목록)
```
action=list, category="투자", status="결정됨", limit=20
```
- 기록된 의사결정 목록을 보여줍니다 (카테고리/상태별 필터 가능)

### action=detail (상세 조회)
```
action=detail, id="결정ID"
```
- 특정 의사결정의 모든 세부 정보를 보여줍니다

### action=update (결과 업데이트)
```
action=update, id="결정ID", result="결과 내용", status="진행중"
```
- 이전에 내린 결정의 결과나 상태를 업데이트합니다
- status: 결정됨/보류/취소/진행중

### action=analyze (패턴 분석)
```
action=analyze
```
- 축적된 의사결정 기록(최소 3건)을 AI가 분석하여 패턴/경향/개선점을 제시합니다

### action=timeline (타임라인)
```
action=timeline, limit=30
```
- 시간순으로 의사결정 연표를 보여줍니다 (영향도별 아이콘, 월별 그룹핑)

## 이 도구를 쓰는 에이전트들

### 1. 비서실장 (chief_of_staff)
**언제 쓰나?** CEO의 모든 주요 결정을 기록하고, 과거 결정을 참조할 때
**어떻게 쓰나?**
- record로 CEO가 내린 중요 결정 즉시 기록
- list/detail로 과거 결정 조회
- analyze로 CEO의 의사결정 패턴 분석 보고

**실전 시나리오:**
> CEO가 "우리가 왜 A 서비스를 포기했었지?" 라고 하면:
> 1. `action=list, category="사업"`으로 사업 관련 결정 검색
> 2. 해당 결정의 `action=detail`로 배경, 이유, 선택지 확인
> 3. CEO에게 구체적으로 보고

### 2. 사업기획처장 (CSO, cso_manager)
**언제 쓰나?** 사업 전략 결정 기록, 경쟁 전략 변경 추적
**어떻게 쓰나?**
- record로 시장 진입/철수, 가격 정책 등 사업 결정 기록
- analyze로 사업 결정 패턴 분석

### 3. 사업계획서 Specialist (business_plan_specialist)
**언제 쓰나?** 사업 계획 수립 시 과거 결정 참고, 재무 의사결정 기록

### 4. 출판/기록처장 (CPO, cpo_manager)
**언제 쓰나?** 회사 연대기에 의사결정 기록 포함, 경영 이력 정리

### 5. 회사연대기 Specialist (chronicle_specialist)
**언제 쓰나?** 회사 역사 기록에 주요 의사결정 포함

### 6. 아카이브 Specialist (archive_specialist)
**언제 쓰나?** 의사결정 기록의 장기 보존, 검색 가능한 형태로 아카이빙

## 주의사항
- 데이터는 data/decisions.json에 저장됩니다 (서버 배포 시 날아갈 수 있으므로 DB 마이그레이션 권장)
- analyze 액션은 최소 3건 이상의 기록이 있어야 작동합니다
- analyze는 AI를 호출하므로 토큰 비용이 발생합니다
- 결정 ID는 8자리 랜덤 문자열입니다 (UUID 앞 8자)
- update는 결과/상태만 업데이트 가능합니다 (결정 내용 자체는 수정 불가)
