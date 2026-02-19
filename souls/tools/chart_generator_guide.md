# chart_generator — 차트 생성기 도구 가이드

## 이 도구는 뭔가요?
숫자 데이터를 눈으로 보기 좋은 차트(그래프)로 바꿔주는 도구입니다.
막대 그래프, 꺾은선 그래프, 원형 그래프, 산점도, 주식 캔들차트, 대시보드까지
다양한 형태의 시각화를 자동으로 생성하여 이미지(PNG) 또는 인터랙티브 HTML 파일로 저장합니다.

## 어떤 API를 쓰나요?
- **matplotlib** (Python 차트 라이브러리) — 막대/꺾은선/원형/산점도 (PNG 이미지)
- **plotly** (인터랙티브 차트 라이브러리) — 캔들차트/대시보드 (HTML 파일)
- 비용: **무료** (모든 기능이 로컬에서 실행)
- 필요한 키: 없음
- 필요 라이브러리: `pip install matplotlib plotly`

## 사용법

### action=bar (막대 그래프)
```
action=bar, labels="1월,2월,3월", values="100,200,300", title="월별 매출", xlabel="월", ylabel="매출(만원)"
```
- 카테고리(항목)별 값을 비교하는 막대 그래프를 생성합니다
- `labels`: X축 항목 — 쉼표로 구분 (필수, 또는 data 사용)
- `values`: Y축 값 — 쉼표로 구분 (필수, 또는 data 사용)
- `data`: JSON 딕셔너리 또는 리스트로 데이터 전달 가능 (labels/values 대체)
- `title`: 차트 제목 (기본값: "막대 그래프")
- `xlabel`: X축 이름, `ylabel`: Y축 이름, `color`: 막대 색상
- 각 막대 위에 값이 자동으로 표시됩니다

**예시:**
- `action=bar, data='{"삼성전자": 350, "SK하이닉스": 180, "LG에너지": 120}', title="시가총액(조원)"`

### action=line (꺾은선 그래프)
```
action=line, labels="1월,2월,3월,4월", values="100,150,130,200", title="매출 추이"
```
- 시간/순서에 따른 변화를 보여주는 꺾은선 그래프를 생성합니다
- 기본 파라미터는 막대 그래프와 동일합니다
- `series`: 다중 시리즈(여러 선)를 한 차트에 표시 가능
  - JSON 형식: `{"매출": [100,200,300], "비용": [80,150,200]}`

**예시:**
- `action=line, labels="1분기,2분기,3분기,4분기", series='{"매출": [100,200,300,400], "비용": [80,150,200,250]}', title="분기별 매출/비용 비교"`

### action=pie (원형 그래프)
```
action=pie, labels="국내주식,해외주식,채권,현금", values="40,30,20,10", title="포트폴리오 구성"
```
- 전체에서 각 항목의 비율을 보여주는 원형 그래프를 생성합니다
- 각 조각에 비율(%)이 자동으로 표시됩니다
- 최대 10가지 색상이 자동 배정됩니다

**예시:**
- `action=pie, data='{"반도체": 45, "바이오": 25, "2차전지": 20, "기타": 10}', title="섹터별 투자 비중"`

### action=scatter (산점도)
```
action=scatter, x="1,2,3,4,5", y="2,4,5,4,6", title="상관관계", xlabel="광고비", ylabel="매출"
```
- 두 변수의 관계를 보여주는 산점도를 생성합니다
- `x`: X축 데이터 — 쉼표 구분 숫자 (필수)
- `y`: Y축 데이터 — 쉼표 구분 숫자 (필수)
- `xlabel`: X축 이름, `ylabel`: Y축 이름

**예시:**
- `action=scatter, x="10,20,30,40,50", y="15,25,35,50,60", title="광고비 vs 매출", xlabel="광고비(만원)", ylabel="매출(만원)"`

### action=candlestick (주식 캔들스틱 차트)
```
action=candlestick, data='[{"date":"2026-01-01","open":50000,"high":52000,"low":49000,"close":51000},...]', title="삼성전자 주가"
```
- 주식의 OHLCV(시가/고가/저가/종가) 데이터를 캔들 차트로 시각화합니다
- `data`: OHLCV 데이터 리스트 (필수) — 각 항목에 date, open, high, low, close 필드
- `title`: 차트 제목
- HTML 파일로 저장되어 브라우저에서 확대/축소/이동이 가능합니다
- 상승(종가>시가)은 빨간색, 하락은 파란색으로 표시됩니다 (한국 주식 관행)
- **plotly 라이브러리가 필요합니다**

### action=dashboard (다중 차트 대시보드)
```
action=dashboard, title="월간 대시보드", charts='[{"type":"bar","title":"매출","labels":["1월","2월","3월"],"values":[100,200,300]},{"type":"line","title":"사용자 수","labels":["1월","2월","3월"],"values":[1000,1500,2000]}]'
```
- 여러 차트를 하나의 대시보드 HTML 파일에 모아서 보여줍니다
- `charts`: 차트 목록 — 각 차트에 type, title, labels, values 포함
- `title`: 대시보드 제목
- 2열 레이아웃으로 자동 배치됩니다
- 지원 차트 유형: "bar", "line", "pie"
- **plotly 라이브러리가 필요합니다**

**예시:**
- `action=dashboard, title="투자 현황", charts='[{"type":"pie","title":"섹터별","labels":["반도체","바이오"],"values":[60,40]},{"type":"bar","title":"수익률","labels":["삼성","SK"],"values":[12.5,8.3]}]'`

## 이 도구를 쓰는 에이전트들

### 1. 사업기획처장 (CSO)
**언제 쓰나?** 사업 데이터를 시각화하여 CEO에게 보고할 때
**어떻게 쓰나?**
- `action=bar`로 경쟁사 비교 차트 생성
- `action=pie`로 시장 점유율 원형 그래프 생성

### 2. 사업계획서 Specialist
**언제 쓰나?** 사업계획서에 들어갈 차트 생성 시
**어떻게 쓰나?**
- `action=bar`로 TAM/SAM/SOM 시장 규모 비교
- `action=line`으로 매출 성장 예측 그래프

### 3. 재무모델링 Specialist
**언제 쓰나?** 재무 분석 결과를 시각화할 때
**어떻게 쓰나?**
- `action=line, series=...`로 3-시나리오(보수/기본/낙관) 비교 그래프
- `action=bar`로 비용 구조 비교

### 4. 투자분석처장 (CIO)
**언제 쓰나?** 투자 포트폴리오 시각화, 시장 데이터 차트 생성 시
**어떻게 쓰나?**
- `action=pie`로 포트폴리오 구성비 차트
- `action=dashboard`로 종합 투자 대시보드 생성

**실전 시나리오:**
> CEO가 "포트폴리오 현황 보여줘" 라고 하면:
> 1. `action=pie, data='{"국내주식": 40, "해외주식": 30, "채권": 20, "현금": 10}', title="포트폴리오 비중"` 생성
> 2. `action=bar, data='{"삼성전자": 12.5, "SK하이닉스": -3.2, "카카오": 5.8}', title="종목별 수익률(%)"` 생성
> 3. 차트 이미지와 함께 분석 요약 보고

### 5. 시황분석 Specialist
**언제 쓰나?** 거시경제 데이터 시각화, 금리/환율 추이 차트 생성 시
**어떻게 쓰나?**
- `action=line`으로 금리/환율/지수 추이 그래프

### 6. 종목분석 Specialist
**언제 쓰나?** 재무 지표 비교, PER/PBR 등 밸류에이션 차트 생성 시
**어떻게 쓰나?**
- `action=bar`로 동종업체 PER/PBR 비교

### 7. 기술적분석 Specialist
**언제 쓰나?** 주가 캔들차트, 기술 지표 대시보드 생성 시
**어떻게 쓰나?**
- `action=candlestick`으로 주가 캔들 차트 생성
- `action=dashboard`로 지표 대시보드 (캔들+RSI+MACD 등) 생성

**실전 시나리오:**
> CEO가 "삼성전자 차트 보여줘" 라고 하면:
> 1. kr_stock 도구로 OHLCV 데이터 수집
> 2. `action=candlestick, data=[...], title="삼성전자 최근 3개월"` 생성
> 3. HTML 파일을 브라우저에서 열어 확대/축소 가능한 차트 제공

### 8. 리스크관리 Specialist
**언제 쓰나?** 리스크 지표 시각화, 상관관계 차트 생성 시
**어떻게 쓰나?**
- `action=scatter`로 자산 간 상관관계 산점도
- `action=bar`로 VaR/CVaR 비교 차트

## 주의사항
- 차트 이미지(PNG)는 `output/charts/` 폴더에 저장됩니다
- 캔들차트와 대시보드(HTML)는 브라우저에서 열어야 합니다
- matplotlib이 없으면 bar/line/pie/scatter를 사용할 수 없습니다
- plotly가 없으면 candlestick/dashboard를 사용할 수 없습니다
- 한글 폰트는 NanumGothic, Malgun Gothic, AppleGothic 순으로 자동 감지합니다 (한글이 깨지면 폰트 설치 필요)
- `data` 파라미터는 JSON 딕셔너리 `{"항목": 값}` 또는 리스트 `[{"name": "항목", "value": 값}]` 형식을 지원합니다
- 리스트 형식 사용 시 `label_key`와 `value_key`로 키 이름을 지정할 수 있습니다 (기본: "name", "value")
