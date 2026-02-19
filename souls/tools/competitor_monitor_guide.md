# competitor_monitor — 경쟁사 웹사이트 감지기 도구 가이드

## 이 도구는 뭔가요?
경쟁사 웹사이트의 변경사항을 자동으로 감지해주는 도구입니다.
감시할 URL을 등록하면 페이지 내용의 스냅샷(사진처럼 저장)을 찍어두고, 다음 확인 시 이전 스냅샷과 비교하여 "뭐가 바뀌었는지" 알려줍니다.
가격 변경, 신제품 출시, 이벤트 시작 등을 자동으로 포착할 수 있습니다.

## 어떤 API를 쓰나요?
- **직접 HTTP 요청** (httpx + BeautifulSoup으로 웹페이지 텍스트 추출)
- **difflib** (Python 내장 라이브러리, 텍스트 차이점 비교)
- **AI 분석** (변경사항의 사업적 의미 분석)
- 비용: **무료**
- 필요한 키: 없음

## 사용법

### action=add (감시 대상 추가)
```
action="add", url="https://www.competitor.com/pricing", name="경쟁사A", selector=".pricing-table"
```
- 감시할 웹사이트 URL을 등록합니다
- 등록 즉시 초기 스냅샷(현재 페이지 상태)을 저장합니다
- selector(CSS 선택자)를 지정하면 페이지의 특정 영역만 감시합니다 (미지정 시 전체 페이지)

**파라미터:**
- `url` (필수): 감시할 웹페이지 주소
- `name` (필수): 경쟁사 이름 (식별용)
- `selector` (선택): CSS 선택자 — 특정 영역만 감시하고 싶을 때 (예: ".price", "#product-list")

**예시:**
- `action="add", url="https://mega-leet.com", name="메가로스쿨"` → 전체 페이지 감시 시작
- `action="add", url="https://mega-leet.com/price", name="메가로스쿨 가격표", selector=".price-table"` → 가격표 영역만 감시

### action=remove (감시 해제)
```
action="remove", url="https://www.competitor.com/pricing"
```
- 감시 목록에서 해당 URL을 제거합니다

### action=list (감시 목록 조회)
```
action="list"
```
- 현재 감시 중인 사이트 전체 목록을 보여줍니다 (이름, URL, 감시 영역, 마지막 확인 시간)

### action=check (변경사항 확인)
```
action="check"
```
- 등록된 모든 사이트의 현재 상태를 가져와 이전 스냅샷과 비교합니다
- 변경이 감지된 사이트에 대해 AI가 사업적 의미를 분석합니다
- 결과: 변경 감지(빨간 불) / 변경 없음 / 접근 실패(경고)
- 확인 후 스냅샷이 자동 갱신됩니다

**예시:**
- `action="check"` → "메가로스쿨: 변경 감지! / 법률저널: 변경 없음" + AI 분석

### action=diff (변경 상세 비교)
```
action="diff", url="https://www.competitor.com/pricing"
```
- 특정 사이트의 이전 버전과 현재 버전의 차이점을 줄 단위로 상세 비교합니다
- 추가된 줄(+), 삭제된 줄(-) 형태로 diff(차이점)를 보여줍니다
- AI가 변경 내용의 요약, 사업적 의미, 대응 전략을 제안합니다

**예시:**
- `action="diff", url="https://mega-leet.com/price"` → 가격표 변경 전후 비교 + "가격 10% 인상 감지, 대응 전략 3가지" 분석

## 이 도구를 쓰는 에이전트들

### 1. CSO 사업기획처장 (cso_manager)
**언제 쓰나?** 경쟁사 동향을 파악하고 사업 전략을 조정할 때
**어떻게 쓰나?**
- add로 주요 경쟁사 웹사이트 등록 (특히 가격 페이지, 서비스 페이지)
- check로 주기적 변경사항 감시
- diff로 구체적 변경 내용 확인 후 전략 보고

**실전 시나리오:**
> CEO가 "경쟁사가 가격을 바꿨다는 소문이 있는데 확인해줘" 라고 하면:
> 1. `action="check"` 로 전체 변경사항 확인
> 2. 변경 감지 시 `action="diff", url="..."` 로 상세 비교
> 3. CEO에게 "경쟁사 A가 기본 패키지 가격을 29만원→35만원으로 인상했습니다. 우리도 가격 조정을 검토하시겠습니까?" 보고

### 2. 시장조사 Specialist (market_research_specialist)
**언제 쓰나?** 경쟁사 웹사이트의 제품/서비스 변경을 추적할 때
**어떻게 쓰나?**
- 경쟁사의 제품 페이지, 이벤트 페이지 등을 add로 등록
- 정기적으로 check 실행하여 변경 추적
- 변경 감지 시 CSO에게 보고

## 주의사항
- 감시 목록은 `data/competitor_watchlist.json`, 스냅샷은 `data/competitor_snapshots/` 에 저장됩니다 (배포 시 날아갈 수 있음)
- 이전 스냅샷 텍스트는 최대 5,000자까지만 저장됩니다 (매우 긴 페이지는 뒷부분이 잘림)
- diff 비교도 최대 200줄까지만 표시됩니다
- JavaScript로 동적 렌더링되는 페이지(SPA)는 정확한 텍스트 추출이 어려울 수 있음
- 로그인이 필요한 페이지는 접근 불가
- selector(CSS 선택자)로 특정 영역만 감시하면 불필요한 변경 알림(광고, 날짜 등)을 줄일 수 있음
