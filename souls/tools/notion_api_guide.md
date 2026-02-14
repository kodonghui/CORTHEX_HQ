# notion_api — 노션 문서 관리 도구 가이드

## 이 도구는 뭔가요?
노션(Notion)에 페이지를 만들고, 수정하고, 검색하는 도구입니다.
실제로 회사 경영지원팀이 노션에 회의록, 기획문서, 위키를 정리하거나
자동화 도구로 데이터를 노션 DB에 넣어서 대시보드를 만드는 것과 같습니다.

## 어떤 API를 쓰나요?
- **Notion API** (api.notion.com)
- 비용: **무료** (노션 워크스페이스만 있으면 됨)
- 필요한 키: `NOTION_API_KEY`, `NOTION_DEFAULT_DB_ID` (데이터베이스 ID)

## 사용법

### action=create_page (새 페이지 생성)
```
action=create_page, title="제목", content="내용"
action=create_page, title="제목", content="내용", tags="태그1,태그2"
```
- 노션에 새 페이지를 만듦
- content는 마크다운 형식 지원 (제목, 목록, 구분선 등)
- tags로 분류 태그 추가 가능

**예시:**
- `action=create_page, title="2026-02 빌딩로그", content="## 이번 달 주요 사건\n- AI 에이전트 도구 12개 추가\n- 텔레그램 연동 완료"`
- `action=create_page, title="삼성전자 분석 보고서", content="...", tags="투자분석,삼성전자"`

### action=update_page (기존 페이지 수정)
```
action=update_page, page_id="페이지ID", content="추가/수정할 내용"
```
- 이미 만들어진 페이지의 내용을 수정

### action=query_db (데이터베이스 조회)
```
action=query_db
action=query_db, filter="조건"
```
- 노션 데이터베이스에서 페이지들을 검색/필터링
- 전체 목록 또는 조건에 맞는 것만 가져오기

### action=list_pages (최근 페이지 목록)
```
action=list_pages, count=10
```
- 최근에 만들어진/수정된 페이지 목록
- count로 가져올 개수 지정

---

## 이 도구를 쓰는 에이전트들

### 1. CPO 처장 (출판기록처장)
**언제 쓰나?** 전체 기록물/출판물을 관리하고 파악할 때
**어떻게 쓰나?**
- `action=list_pages, count=20` → 최근 기록물 전체 현황 파악
- `action=query_db` → 특정 카테고리의 문서들 조회
- Specialist들이 만든 기록을 검토하고 관리

**실전 시나리오:**
> CEO가 "우리 회사 기록물 현황 보고해" 라고 하면:
> 1. `notion_api action=list_pages, count=50` → 전체 페이지 목록
> 2. 카테고리별 분류: 빌딩로그 12건, 분석보고서 8건, 회의록 5건...
> 3. **보고:** "총 25건의 기록물. 빌딩로그가 가장 많고, 최근 1주일간 5건 추가됨"

### 2. 회사연대기 Specialist
**언제 쓰나?** 빌딩로그, 의사결정 기록을 작성하고 저장할 때
**어떻게 쓰나?**
- 기록을 작성한 후 → `action=create_page`로 노션에 영구 저장
- 기존 기록에 추가 → `action=update_page`로 업데이트
- 이전 기록 참조 → `action=list_pages`로 관련 기록 찾기

**실전 시나리오:**
> CEO가 "오늘 있었던 일 기록해" 라고 하면:
> 1. CEO와의 대화 내용을 정리
> 2. `notion_api action=create_page, title="2026-02-14 빌딩로그: AI 도구 12개 구축", content="## 오늘 한 일\n- 5개 부서에 전문가 도구 12개 구축\n- ..."`
> 3. **완료:** "노션에 빌딩로그 저장 완료. 페이지 링크: ..."

### 3. 아카이브 Specialist
**언제 쓰나?** 모든 기록물을 체계적으로 분류/정리할 때
**어떻게 쓰나?**
- `action=query_db` → 전체 문서 목록에서 미분류 문서 찾기
- `action=create_page, tags="..."` → 태그 달아서 분류
- `action=list_pages` → 정리 현황 확인
- doc_converter(문서 변환)와 함께 → 중요 문서는 PDF로도 백업

---

## 주의사항
- `NOTION_API_KEY`와 `NOTION_DEFAULT_DB_ID`가 설정되어 있어야 합니다.
- 노션 워크스페이스에 API 연동(Integration)을 먼저 설정해야 합니다.
- 한 번에 너무 많은 페이지를 조회하면 느려질 수 있습니다.
- 마크다운 → 노션 블록 변환 시 일부 서식이 달라질 수 있습니다.
