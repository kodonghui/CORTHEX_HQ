# kipris — 특허/상표/디자인 검색 도구 가이드

## 이 도구는 뭔가요?
특허정보원(KIPRIS)에서 특허, 상표, 디자인 등록 현황을 검색하는 도구입니다.
실제로 변리사(특허 전문 변호사)가 특허 출원 전에 "이미 비슷한 특허가 있나?" 조사하는 것과 같습니다.

## 어떤 API를 쓰나요?
- **KIPRIS Plus API** (plus.kipris.or.kr) — 특허정보원 운영
- 비용: **무료**
- 필요한 키: `KIPRIS_API_KEY`

## 사용법

### action=patent (특허 검색)
```
action=patent, query="기술 키워드"
```
- 등록/출원된 특허를 키워드로 검색
- 특허명, 출원인, 출원일, 등록일 등 반환

**예시:**
- `action=patent, query="AI 학습 데이터"` → AI 관련 특허 목록
- `action=patent, query="자연어처리 교육"` → NLP 교육 관련 특허

### action=trademark (상표 검색)
```
action=trademark, query="상표명"
```
- 등록/출원된 상표를 검색
- 상표명, 출원인, 지정상품, 등록 상태 반환

**예시:**
- `action=trademark, query="CORTHEX"` → CORTHEX 상표 등록 현황
- `action=trademark, query="LEET Master"` → LEET Master 상표 존재 여부

### action=design (디자인 검색)
```
action=design, query="디자인명"
```
- 등록된 디자인(제품 외관)을 검색

---

## 이 도구를 쓰는 에이전트들

### 1. 특허/약관 Specialist
**언제 쓰나?** 특허 출원 전 선행기술 조사, 상표 등록 전 중복 확인
**어떻게 쓰나?**
- **특허 출원 전:** `action=patent`로 비슷한 특허가 이미 있는지 확인 (이걸 "선행기술 조사"라고 함)
- **상표 등록 전:** `action=trademark`로 같은 이름이 이미 등록됐는지 확인
- law_search(법령검색)과 함께 → 특허법 근거 + 실제 등록 현황 종합

**실전 시나리오 — 상표 등록 검토:**
> CEO가 "CORTHEX라는 이름 상표 등록할 수 있어?" 라고 물으면:
> 1. `kipris action=trademark, query="CORTHEX"` → 기존 등록 없음 확인
> 2. `kipris action=trademark, query="코텍스"` → 유사 발음 상표 확인
> 3. `law_search action=law, query="상표법"` → 등록 요건 확인
> 4. **결론:** "CORTHEX 동일 상표 없음, 유사 상표 없음 → 등록 가능성 높음"

**실전 시나리오 — 특허 출원 검토:**
> "AI 기반 학습 분석 기능에 특허 낼 수 있어?":
> 1. `kipris action=patent, query="AI 학습 분석"` → 유사 특허 5건 발견
> 2. `kipris action=patent, query="자연어처리 교육 콘텐츠"` → 유사 특허 2건
> 3. **분석:** "유사 특허 존재하나, 우리 기술의 차별점(에이전트 조직 구조)이 명확하면 출원 가능"

### 2. 저작권 Specialist
**언제 쓰나?** 상표/디자인 관련 저작권 이슈 확인할 때
**어떻게 쓰나?**
- `action=trademark`로 상표 충돌 여부 확인
- `action=design`으로 디자인 등록 현황 확인

---

## 주의사항
- 특허/상표 등록 여부와 "사용해도 되는지"는 별개 문제입니다. 법적 판단은 변리사와 상담하세요.
- 검색 결과가 없다고 100% 안전한 것은 아닙니다 (출원 중이거나 해외 등록 가능).
- 특허 검색은 키워드가 구체적일수록 정확한 결과가 나옵니다.
