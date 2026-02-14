# doc_converter — 문서 변환 도구 가이드

## 이 도구는 뭔가요?
마크다운(.md) 파일을 PDF, Word(.docx), 전자책(.epub)으로 변환하는 도구입니다.
한글 폰트가 자동으로 적용되어 한국어 문서도 깨지지 않습니다.
실제로 출판사나 편집팀이 원고를 여러 형식으로 변환해서 배포하는 것과 같습니다.

## 어떤 기술을 쓰나요?
- **pandoc** — 문서 변환 엔진 (로컬 프로그램)
- **LaTeX** (xelatex/pdflatex) — PDF 생성 엔진
- 비용: **완전 무료** (로컬에서 실행, API 키 불필요)
- 한글 폰트: NanumGothic 자동 적용

## 사용법

### action=to_pdf (PDF 변환)
```
action=to_pdf, input_file="파일경로"
```
- 마크다운 파일을 PDF로 변환
- 한글 폰트(나눔고딕) 자동 적용
- 출력: `output/` 폴더에 저장

**예시:**
- `action=to_pdf, input_file="docs/report.md"` → `output/report.pdf`

**용도:** 인쇄용, 공식 문서, 영구 보관용

### action=to_docx (Word 변환)
```
action=to_docx, input_file="파일경로"
```
- 마크다운 파일을 Word 문서로 변환
- 수정 가능한 형식이라 추가 편집에 적합

**예시:**
- `action=to_docx, input_file="docs/plan.md"` → `output/plan.docx`

**용도:** 수정/편집이 필요할 때, 외부 공유용

### action=to_epub (전자책 변환)
```
action=to_epub, input_file="파일경로"
```
- 마크다운 파일을 EPUB(전자책) 형식으로 변환
- 킨들, 리디북스 등 전자책 리더에서 읽을 수 있음

**예시:**
- `action=to_epub, input_file="docs/book.md"` → `output/book.epub`

**용도:** 전자책 출판, 모바일 읽기용

---

## 이 도구를 쓰는 에이전트들

### 1. 콘텐츠편집 Specialist
**언제 쓰나?** 편집 완료된 글을 배포 형식으로 변환할 때
**어떻게 쓰나?**
- 글 편집/퇴고 완료 후 → 배포 목적에 따라 형식 선택
  - 공식 문서/인쇄 → `action=to_pdf`
  - 추가 편집 필요 → `action=to_docx`
  - 전자책 배포 → `action=to_epub`
- translator(번역 도구)와 함께 → 번역 후 변환

**실전 시나리오:**
> CEO가 "지난달 빌딩로그를 PDF로 만들어줘" 라고 하면:
> 1. 빌딩로그 마크다운 파일 편집/검수
> 2. `doc_converter action=to_pdf, input_file="docs/building-log-2026-01.md"`
> 3. **완료:** "PDF 생성 완료. output/building-log-2026-01.pdf"

### 2. 아카이브 Specialist
**언제 쓰나?** 기록물을 영구 보관 형식으로 변환할 때
**어떻게 쓰나?**
- 중요 기록물 → `action=to_pdf`로 PDF 백업 생성
- 외부 공유가 필요한 문서 → `action=to_docx`로 Word 변환
- notion_api(노션)와 함께 → 노션에 기록 + PDF로 백업

**실전 시나리오:**
> 분기별 아카이브 정리:
> 1. `notion_api action=list_pages, count=50` → 이번 분기 기록물 목록
> 2. 중요 문서 선별
> 3. `doc_converter action=to_pdf, input_file="docs/q1-summary.md"` → PDF 생성
> 4. **결과:** "2026년 1분기 기록물 15건 중 핵심 5건 PDF 아카이브 완료"

---

## 주의사항
- pandoc이 설치되어 있어야 합니다. 없으면 동작하지 않습니다.
- PDF 변환에는 LaTeX(xelatex 또는 pdflatex)도 필요합니다.
- 이미지가 포함된 마크다운은 이미지 경로가 올바른지 확인하세요.
- 변환된 파일은 `output/` 폴더에 저장됩니다.
