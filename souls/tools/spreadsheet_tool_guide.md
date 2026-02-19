# spreadsheet_tool — 스프레드시트 도구 가이드

## 이 도구는 뭔가요?
엑셀(xlsx)이나 CSV 파일을 읽고, 쓰고, 분석하는 도구입니다.
파일을 열어서 데이터를 미리보기 하거나, 통계 분석(평균/합계/분포 등)을 하거나,
특정 조건으로 필터링하거나, 피벗 테이블(집계표)을 만들 수 있습니다.

## 어떤 API를 쓰나요?
- **pandas** (Python 데이터 분석 라이브러리) — 파일 읽기/쓰기/분석
- **openpyxl** (엑셀 파일 처리 라이브러리) — xlsx 파일 지원
- AI 분석에서 LLM 호출이 발생합니다
- 비용: **무료** (모든 기능이 로컬에서 실행)
- 필요한 키: 없음
- 필요 라이브러리: `pip install pandas openpyxl`

## 사용법

### action=read (파일 읽기)
```
action=read, file_path="data/report.xlsx", sheet_name="Sheet1", max_rows=20
```
- 엑셀/CSV 파일을 열어서 내용을 보여줍니다
- `file_path`: 파일 경로 (필수)
- `sheet_name`: 엑셀 시트 이름 (선택, 기본값: 첫 번째 시트)
- `max_rows`: 미리보기 행 수 (기본값: 20행)
- 전체 행/열 수, 컬럼 타입, 미리보기 표를 반환합니다

**지원 형식:** xlsx, xls, csv, tsv

**예시:**
- `action=read, file_path="data/sales.csv"` → 매출 CSV 파일 미리보기
- `action=read, file_path="data/report.xlsx", max_rows=50` → 엑셀 파일 상위 50행 보기

### action=write (파일 저장)
```
action=write, file_path="output/result.xlsx", data=[{"이름": "삼성", "매출": 100}, {"이름": "LG", "매출": 80}], sheet_name="Sheet1"
```
- 데이터를 엑셀/CSV 파일로 저장합니다
- `file_path`: 저장할 파일 경로 (필수)
- `data`: 저장할 데이터 — dict 리스트 또는 JSON 문자열 (필수)
- `sheet_name`: 엑셀 시트 이름 (기본값: "Sheet1")
- 디렉토리가 없으면 자동 생성됩니다

**예시:**
- `action=write, file_path="output/종목비교.xlsx", data='[{"종목":"삼성전자","PER":12.5},{"종목":"SK하이닉스","PER":8.3}]'`

### action=analyze (데이터 통계 분석)
```
action=analyze, file_path="data/sales.csv"
```
- 파일의 통계 요약(평균, 표준편차, 최소/최대, 분위수)을 자동 계산합니다
- `file_path`: 분석할 파일 (필수)
- `sheet_name`: 엑셀 시트 이름 (선택)
- 결측값(빈 칸) 현황도 함께 표시합니다
- AI가 통계를 해석하여 핵심 인사이트를 쉽게 설명해줍니다

**예시:**
- `action=analyze, file_path="data/매출현황.xlsx"` → 매출 데이터 통계 + AI 인사이트

### action=filter (조건별 필터링)
```
action=filter, file_path="data/stocks.csv", column="PER", operator="<", value=10
```
- 특정 조건에 맞는 행만 걸러냅니다
- `file_path`: 파일 경로 (필수)
- `column`: 필터링할 컬럼 이름 (필수)
- `operator`: 비교 연산자 — "==", "!=", ">", ">=", "<", "<=", "contains" (필수)
- `value`: 비교 값 (필수)
- `max_rows`: 결과 표시 행 수 (기본값: 50)

**예시:**
- `action=filter, file_path="data/stocks.csv", column="PER", operator="<", value=10` → PER이 10 미만인 종목만 필터
- `action=filter, file_path="data/고객.csv", column="이름", operator="contains", value="김"` → 이름에 "김"이 포함된 행

### action=pivot (피벗 테이블 생성)
```
action=pivot, file_path="data/sales.csv", index="부서", values="매출", aggfunc="sum"
```
- 데이터를 그룹별로 집계하는 피벗 테이블을 만듭니다
- `file_path`: 파일 경로 (필수)
- `index`: 행 기준 컬럼 (필수) — 그룹핑 기준
- `values`: 집계할 값 컬럼 (필수)
- `columns`: 열 기준 컬럼 (선택)
- `aggfunc`: 집계 함수 — "sum"(합계), "mean"(평균), "count"(개수) (기본값: "sum")

**예시:**
- `action=pivot, file_path="data/sales.csv", index="월", values="매출", aggfunc="sum"` → 월별 매출 합계
- `action=pivot, file_path="data/sales.csv", index="부서", columns="분기", values="매출", aggfunc="mean"` → 부서별/분기별 평균 매출

## 이 도구를 쓰는 에이전트들

### 1. 사업기획처장 (CSO)
**언제 쓰나?** 시장 데이터 분석, 사업 데이터 정리 시
**어떻게 쓰나?**
- `action=read`로 수집된 데이터 파일 확인
- `action=analyze`로 시장 데이터 통계 분석
- `action=write`로 분석 결과를 엑셀로 저장하여 공유

### 2. 사업계획서 Specialist
**언제 쓰나?** 재무 데이터 분석, 사업계획서용 데이터 정리 시
**어떻게 쓰나?**
- `action=analyze`로 재무 데이터 통계 확인
- `action=filter`로 특정 조건의 데이터만 추출

### 3. 재무모델링 Specialist
**언제 쓰나?** 재무 모델 데이터를 엑셀로 저장하거나 분석할 때
**어떻게 쓰나?**
- `action=write`로 DCF/손익 분석 결과를 엑셀로 저장
- `action=pivot`으로 기간별/항목별 재무 데이터 집계

### 4. 투자분석처장 (CIO)
**언제 쓰나?** 투자 포트폴리오 데이터 관리, 종목 비교 시
**어떻게 쓰나?**
- `action=read`로 포트폴리오 데이터 확인
- `action=filter`로 특정 조건의 종목 필터링 (예: PER < 10)

### 5. 종목분석 Specialist
**언제 쓰나?** 재무제표 데이터 비교, 동종업체 분석 시
**어떻게 쓰나?**
- `action=write`로 종목 비교표를 엑셀로 저장
- `action=analyze`로 재무 지표 통계 분석

**실전 시나리오:**
> CEO가 "반도체 종목 비교표 만들어줘" 라고 하면:
> 1. 종목 데이터를 수집하여 비교 데이터 구성
> 2. `action=write, file_path="output/반도체_비교.xlsx", data=[...]`로 엑셀 저장
> 3. `action=analyze`로 통계 분석 추가
> 4. CEO에게 엑셀 파일과 핵심 인사이트 함께 보고

### 6. 기술적분석 Specialist
**언제 쓰나?** 주가 데이터를 정리하거나 백테스트 결과를 저장할 때
**어떻게 쓰나?**
- `action=write`로 기술 지표 데이터를 엑셀로 저장
- `action=filter`로 특정 시그널이 발생한 날짜만 추출

## 주의사항
- pandas와 openpyxl 라이브러리가 설치되어 있어야 합니다
- 지원 형식: xlsx, xls, csv, tsv (다른 형식은 에러)
- CSV 파일은 UTF-8-BOM 인코딩으로 읽고 씁니다 (한글 깨짐 방지)
- 엑셀 쓰기 시 디렉토리가 없으면 자동 생성됩니다
- `action=analyze`의 AI 인사이트는 통계 요약을 기반으로 한 해석이므로, 실제 비즈니스 맥락은 사용자가 판단해야 합니다
- 피벗 테이블의 `aggfunc`는 "sum", "mean", "count" 등 pandas가 지원하는 함수를 사용할 수 있습니다
