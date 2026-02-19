# pdf_parser — PDF 파서 도구 가이드

## 이 도구는 뭔가요?
PDF 파일에서 텍스트와 표(테이블)를 자동으로 뽑아주는 도구입니다.
계약서, 보고서, 논문 같은 PDF 문서를 열어서 글자를 추출하거나, 표를 마크다운 형식으로 변환하고, 특정 페이지만 골라 읽거나, 원하는 단어를 검색할 수 있습니다.
AI가 PDF 내용을 요약해주는 기능도 있습니다.

## 어떤 API를 쓰나요?
- **PyMuPDF (fitz)** — 텍스트 추출, 페이지별 추출, 텍스트 검색에 사용
- **pdfplumber** — 표(테이블) 추출에 사용
- 비용: **무료** (오픈소스 라이브러리)
- 필요한 키: 없음 (summary 액션에서 AI 요약 시 에이전트의 기본 AI 모델 사용)

## 사용법

### action=extract (전체 텍스트 추출)
```
action=extract, file_path="/path/to/document.pdf"
```
- PDF 전체 페이지의 텍스트를 한 번에 추출합니다
- 각 페이지마다 "--- 페이지 1/10 ---" 구분선이 붙어서 어느 페이지인지 알 수 있습니다
- 반환: 파일명, 총 페이지 수, 추출 글자 수, 전체 텍스트

**예시:**
- `action=extract, file_path="/home/ubuntu/docs/contract.pdf"` → 계약서 전문 텍스트 추출

### action=tables (표 추출)
```
action=tables, file_path="/path/to/document.pdf"
```
- PDF 안에 있는 표(테이블)를 찾아서 마크다운 표 형식으로 변환합니다
- 여러 페이지에 걸쳐 있는 표도 각각 추출됩니다
- 반환: 발견된 표 개수, 마크다운 형식의 표 데이터

**예시:**
- `action=tables, file_path="/home/ubuntu/docs/financial_report.pdf"` → 재무보고서의 표 추출

### action=pages (특정 페이지 추출)
```
action=pages, file_path="/path/to/document.pdf", pages="1-3,5"
```
- 원하는 페이지만 골라서 텍스트를 추출합니다
- pages 형식: "1-3" (1~3페이지), "1,3,5" (1, 3, 5페이지), "1-3,5,7-9" (조합 가능)
- 반환: 요청한 페이지의 텍스트

**예시:**
- `action=pages, file_path="/home/ubuntu/docs/thesis.pdf", pages="1-5"` → 논문 앞부분 5페이지만 추출

### action=summary (AI 요약)
```
action=summary, file_path="/path/to/document.pdf", max_chars=15000
```
- PDF 텍스트를 추출한 뒤, AI가 문서 유형/핵심 내용/주요 수치/특이사항을 구조적으로 요약합니다
- max_chars: AI에게 전달할 최대 글자 수 (기본값 15,000자, 너무 긴 문서는 앞부분만 요약)
- 반환: 문서 유형, 핵심 내용, 주요 수치/데이터, 특이사항

**예시:**
- `action=summary, file_path="/home/ubuntu/docs/research_paper.pdf"` → 연구 논문 핵심 요약

### action=search (텍스트 검색)
```
action=search, file_path="/path/to/document.pdf", keyword="검색어"
```
- PDF 전체에서 특정 단어/문구를 검색합니다
- 대소문자 구분 없이 검색하며, 키워드 전후 100자의 맥락(주변 텍스트)을 함께 보여줍니다
- 반환: 발견 횟수, 각 발견 위치(페이지 번호)와 주변 텍스트

**예시:**
- `action=search, file_path="/home/ubuntu/docs/contract.pdf", keyword="위약금"` → 계약서에서 "위약금" 관련 조항 찾기

## 이 도구를 쓰는 에이전트들

### 1. 콘텐츠편집 Specialist (editor_specialist)
**언제 쓰나?** 편집할 원고가 PDF로 들어왔을 때, 또는 참고 자료 PDF에서 내용을 뽑아야 할 때
**어떻게 쓰나?**
- extract로 전체 텍스트를 뽑아 편집 작업의 원문으로 사용
- summary로 긴 PDF 자료를 빠르게 파악한 뒤 편집 방향 결정
- search로 특정 키워드 관련 부분만 찾아서 인용

**실전 시나리오:**
> CEO가 "이 PDF 보고서를 뉴스레터로 만들어줘" 라고 하면:
> 1. `action=extract`로 PDF 전체 텍스트 추출
> 2. `action=summary`로 핵심 내용 파악
> 3. 추출된 내용을 바탕으로 뉴스레터 형식으로 편집

### 2. 아카이브 Specialist (archive_specialist)
**언제 쓰나?** 회사 문서를 아카이빙(보관/정리)할 때, PDF 문서를 지식베이스에 등록할 때
**어떻게 쓰나?**
- extract로 PDF 텍스트를 뽑아서 vector_knowledge 도구에 저장
- tables로 재무 데이터 등 표 정보를 구조화해서 보관
- search로 기존 아카이브 PDF에서 필요한 정보 검색

**실전 시나리오:**
> CEO가 "지난달 투자 보고서 PDF를 지식베이스에 넣어줘" 라고 하면:
> 1. `action=extract`로 PDF 텍스트 추출
> 2. 추출된 텍스트를 vector_knowledge의 `action=add_file`로 벡터 DB에 저장
> 3. 나중에 "지난달 수익률이 얼마였지?" 같은 질문에 검색 가능

## 주의사항
- 스캔(사진으로 찍은) PDF는 텍스트 추출이 안 됩니다 (OCR 기능 없음)
- 표 추출(tables)은 pdfplumber를 사용하므로, 표가 이미지로 삽입된 경우에는 추출 불가
- summary 액션은 AI를 호출하므로 토큰 비용이 발생합니다
- 매우 큰 PDF(수백 페이지)는 pages 액션으로 범위를 지정하여 부분 추출하는 것이 효율적입니다
