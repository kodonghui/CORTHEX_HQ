# vector_knowledge — 벡터 지식베이스 도구 가이드

## 이 도구는 뭔가요?
회사의 지식(보고서, 매뉴얼, 회의록 등)을 AI가 이해할 수 있는 형태로 저장하고, 자연어(일상 언어)로 검색할 수 있게 해주는 도구입니다.
일반적인 키워드 검색과 달리, "의미가 비슷한" 내용을 찾아줍니다. 예를 들어 "매출 성장"이라고 검색하면 "수익 증가", "실적 호조" 같은 비슷한 의미의 문서도 함께 찾아줍니다.
이 기술을 RAG(Retrieval-Augmented Generation, 검색 보강 생성)라고 합니다.

## 어떤 API를 쓰나요?
- **ChromaDB** — 벡터 데이터베이스(벡터를 저장하고 검색하는 전문 DB)
- **OpenAI Embeddings API** (모델: `text-embedding-3-small`) — 텍스트를 벡터로 변환
- 비용: **유료** (임베딩 비용 약 $0.02/1M 토큰, 매우 저렴)
- 필요한 키: `OPENAI_API_KEY`
- 저장 경로: `data/vector_db/` (서버에서 영구 저장)

## 사용법

### action=search (의미 기반 검색)
```
action=search, query="검색할 내용", collection="default", top_k=5
```
- 자연어로 질문하면 의미가 가장 비슷한 문서를 찾아주고, AI가 그 문서를 기반으로 답변합니다
- collection: 검색할 지식 그룹 이름 (기본값: default)
- top_k: 찾을 문서 수 (기본값: 5개)
- 반환: 유사도 점수별 문서 목록 + AI의 종합 답변

**예시:**
- `action=search, query="지난달 투자 수익률은?"` → 저장된 투자 보고서에서 관련 내용을 찾아 답변

### action=add (지식 추가)
```
action=add, text="저장할 텍스트", collection="default", source="출처 정보"
```
- 텍스트를 벡터로 변환해서 지식베이스에 저장합니다
- collection: 저장할 지식 그룹 이름 (기본값: default, 없으면 자동 생성)
- source: 출처 정보 (예: "2026년 1분기 보고서")

**예시:**
- `action=add, text="2026년 1분기 매출은 5억원으로 전년 대비 20% 증가했다.", collection="finance", source="1분기 실적보고서"`

### action=add_file (파일 일괄 추가)
```
action=add_file, file_path="/path/to/document.pdf", collection="default", chunk_size=500, overlap=50
```
- 파일(PDF, TXT, MD, CSV) 전체를 자동으로 청크(조각)로 나누어 일괄 저장합니다
- chunk_size: 한 조각의 글자 수 (기본값: 500자)
- overlap: 조각 간 겹치는 글자 수 (기본값: 50자, 문맥 유지를 위해)

**예시:**
- `action=add_file, file_path="/home/ubuntu/docs/annual_report.pdf", collection="reports"` → 연간 보고서를 500자씩 잘라서 일괄 저장

### action=list (컬렉션 목록)
```
action=list
```
- 저장된 모든 지식 그룹(컬렉션)과 각각의 문서 수를 보여줍니다

### action=delete (지식 삭제)
```
action=delete, collection="컬렉션이름", doc_id="문서ID(선택)"
```
- 특정 문서 1개를 삭제하거나, 컬렉션 전체를 삭제합니다

### action=stats (통계)
```
action=stats
```
- 지식베이스 전체 현황을 보여줍니다 (컬렉션 수, 총 문서 수, 임베딩 모델 등)

## 이 도구를 쓰는 에이전트들

### 1. AI 모델 Specialist (ai_model_specialist)
**언제 쓰나?** 에이전트 지식베이스 구축, RAG 검색 성능 테스트, 벡터 DB 관리
**어떻게 쓰나?**
- add_file로 회사 문서를 일괄 벡터화하여 지식베이스 구축
- search로 검색 정확도 테스트
- stats로 지식베이스 규모 모니터링

**실전 시나리오:**
> CEO가 "에이전트들이 회사 내부 정보도 알게 해줘" 라고 하면:
> 1. 회사 주요 문서를 `action=add_file`로 일괄 등록
> 2. 컬렉션을 분야별로 나눔 (finance, legal, tech 등)
> 3. `action=search`로 검색 품질 테스트

### 2. 아카이브 Specialist (archive_specialist)
**언제 쓰나?** 회사 문서 아카이빙(보관), 과거 기록 검색, 지식 자산 관리
**어떻게 쓰나?**
- add/add_file로 과거 보고서, 회의록을 체계적으로 저장
- search로 과거 기록에서 필요한 정보 즉시 검색
- pdf_parser와 연동하여 PDF 문서를 텍스트로 변환 후 저장

**실전 시나리오:**
> CEO가 "3개월 전 우리가 왜 그 결정을 했었지?" 라고 하면:
> 1. `action=search, query="3개월 전 결정 배경"` 으로 관련 기록 검색
> 2. 유사도가 높은 문서들을 기반으로 AI가 답변 생성

## 주의사항
- 첫 사용 전 지식을 먼저 추가(add/add_file)해야 검색이 가능합니다
- ChromaDB 라이브러리가 서버에 설치되어 있어야 합니다 (pip install chromadb)
- chunk_size가 너무 작으면 문맥이 끊기고, 너무 크면 검색 정밀도가 떨어집니다 (500자 권장)
- 데이터는 data/vector_db/ 디렉토리에 저장됩니다
- search 결과에서 유사도가 낮으면 관련 없는 문서일 수 있으므로 주의하세요
