"""PDF 파서 도구 — PDF 파일에서 텍스트/표 추출."""
from __future__ import annotations

import logging
import os
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.pdf_parser")


def _get_fitz():
    """PyMuPDF 지연 임포트."""
    try:
        import fitz
        return fitz
    except ImportError:
        return None


def _get_pdfplumber():
    """pdfplumber 지연 임포트."""
    try:
        import pdfplumber
        return pdfplumber
    except ImportError:
        return None


class PdfParserTool(BaseTool):
    """PDF 파일에서 텍스트와 표를 추출하는 도구."""

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "extract")
        if action == "extract":
            return await self._extract(kwargs)
        elif action == "tables":
            return await self._tables(kwargs)
        elif action == "pages":
            return await self._pages(kwargs)
        elif action == "summary":
            return await self._summary(kwargs)
        elif action == "search":
            return await self._search(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능한 action: extract(텍스트 추출), tables(표 추출), "
                "pages(페이지별 추출), summary(요약), search(텍스트 검색)"
            )

    # ── 내부 메서드 ──

    @staticmethod
    def _check_file(file_path: str) -> str | None:
        """파일 존재 여부 확인. 문제 없으면 None 반환."""
        if not file_path:
            return "파일 경로(file_path)를 입력해주세요."
        if not os.path.isfile(file_path):
            return f"파일을 찾을 수 없습니다: {file_path}"
        if not file_path.lower().endswith(".pdf"):
            return f"PDF 파일이 아닙니다: {file_path}"
        return None

    async def _extract(self, kwargs: dict) -> str:
        """전체 텍스트 추출."""
        file_path = kwargs.get("file_path", "")
        err = self._check_file(file_path)
        if err:
            return err

        fitz = _get_fitz()
        if fitz is None:
            return "PyMuPDF 라이브러리가 설치되지 않았습니다. pip install PyMuPDF"

        try:
            doc = fitz.open(file_path)
            total_pages = len(doc)
            texts: list[str] = []
            for i, page in enumerate(doc):
                text = page.get_text()
                if text.strip():
                    texts.append(f"--- 페이지 {i + 1}/{total_pages} ---\n{text.strip()}")
            doc.close()

            if not texts:
                return f"PDF에서 텍스트를 추출할 수 없습니다 (스캔 PDF일 수 있음): {file_path}"

            result = "\n\n".join(texts)
            char_count = len(result)
            logger.info("PDF 텍스트 추출 완료: %s (%d페이지, %d자)", file_path, total_pages, char_count)
            return f"## PDF 텍스트 추출 결과\n\n- 파일: {file_path}\n- 총 페이지: {total_pages}\n- 추출 글자 수: {char_count:,}\n\n{result}"

        except Exception as e:
            logger.error("PDF 텍스트 추출 실패: %s", e)
            return f"PDF 텍스트 추출 중 오류 발생: {e}"

    async def _tables(self, kwargs: dict) -> str:
        """PDF 내 표(table) 추출."""
        file_path = kwargs.get("file_path", "")
        err = self._check_file(file_path)
        if err:
            return err

        pdfplumber = _get_pdfplumber()
        if pdfplumber is None:
            return "pdfplumber 라이브러리가 설치되지 않았습니다. pip install pdfplumber"

        try:
            all_tables: list[str] = []
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    tables = page.extract_tables()
                    for t_idx, table in enumerate(tables):
                        if not table:
                            continue
                        # 마크다운 테이블로 변환
                        header = table[0] if table else []
                        md_lines = [f"### 페이지 {i + 1} - 표 {t_idx + 1}\n"]
                        md_lines.append("| " + " | ".join(str(c or "") for c in header) + " |")
                        md_lines.append("| " + " | ".join("---" for _ in header) + " |")
                        for row in table[1:]:
                            md_lines.append("| " + " | ".join(str(c or "") for c in row) + " |")
                        all_tables.append("\n".join(md_lines))

            if not all_tables:
                return f"PDF에서 표를 찾을 수 없습니다: {file_path}"

            result = "\n\n".join(all_tables)
            logger.info("PDF 표 추출 완료: %s (%d개 표)", file_path, len(all_tables))
            return f"## PDF 표 추출 결과\n\n- 파일: {file_path}\n- 발견된 표: {len(all_tables)}개\n\n{result}"

        except Exception as e:
            logger.error("PDF 표 추출 실패: %s", e)
            return f"PDF 표 추출 중 오류 발생: {e}"

    async def _pages(self, kwargs: dict) -> str:
        """특정 페이지만 추출."""
        file_path = kwargs.get("file_path", "")
        err = self._check_file(file_path)
        if err:
            return err

        fitz = _get_fitz()
        if fitz is None:
            return "PyMuPDF 라이브러리가 설치되지 않았습니다. pip install PyMuPDF"

        # 페이지 범위 파싱 (예: "1-3" 또는 "1,3,5")
        page_spec = kwargs.get("pages", "1")
        try:
            page_nums = self._parse_page_spec(page_spec)
        except ValueError as e:
            return f"잘못된 페이지 지정: {e}"

        try:
            doc = fitz.open(file_path)
            total_pages = len(doc)
            texts: list[str] = []
            for p in page_nums:
                if p < 1 or p > total_pages:
                    texts.append(f"--- 페이지 {p}: 범위 초과 (총 {total_pages}페이지) ---")
                    continue
                text = doc[p - 1].get_text()
                texts.append(f"--- 페이지 {p}/{total_pages} ---\n{text.strip() if text.strip() else '(텍스트 없음)'}")
            doc.close()

            return f"## 페이지별 추출 결과\n\n- 파일: {file_path}\n- 요청 페이지: {page_spec}\n\n" + "\n\n".join(texts)

        except Exception as e:
            return f"페이지 추출 중 오류 발생: {e}"

    async def _summary(self, kwargs: dict) -> str:
        """PDF 내용 요약."""
        file_path = kwargs.get("file_path", "")
        err = self._check_file(file_path)
        if err:
            return err

        # 먼저 텍스트 추출
        extract_result = await self._extract(kwargs)
        if "오류" in extract_result or "찾을 수 없습니다" in extract_result:
            return extract_result

        # 너무 긴 텍스트는 앞부분만
        max_chars = int(kwargs.get("max_chars", 15000))
        text_for_summary = extract_result[:max_chars]

        summary = await self._llm_call(
            system_prompt=(
                "당신은 문서 요약 전문가입니다. "
                "PDF에서 추출한 텍스트를 읽고 핵심 내용을 한국어로 구조적으로 요약하세요.\n"
                "1. 문서 유형 (계약서, 보고서, 논문 등)\n"
                "2. 핵심 내용 (5줄 이내)\n"
                "3. 주요 수치/데이터\n"
                "4. 특이사항/주의점"
            ),
            user_prompt=text_for_summary,
        )

        return f"## PDF 요약\n\n- 파일: {file_path}\n\n{summary}"

    async def _search(self, kwargs: dict) -> str:
        """PDF 내 텍스트 검색."""
        file_path = kwargs.get("file_path", "")
        keyword = kwargs.get("keyword", "")
        err = self._check_file(file_path)
        if err:
            return err
        if not keyword:
            return "검색어(keyword)를 입력해주세요."

        fitz = _get_fitz()
        if fitz is None:
            return "PyMuPDF 라이브러리가 설치되지 않았습니다. pip install PyMuPDF"

        try:
            doc = fitz.open(file_path)
            findings: list[str] = []
            for i, page in enumerate(doc):
                text = page.get_text()
                if keyword.lower() in text.lower():
                    # 키워드 주변 텍스트 추출
                    lower_text = text.lower()
                    idx = lower_text.find(keyword.lower())
                    start = max(0, idx - 100)
                    end = min(len(text), idx + len(keyword) + 100)
                    context = text[start:end].strip()
                    findings.append(f"- **페이지 {i + 1}**: ...{context}...")
            doc.close()

            if not findings:
                return f"'{keyword}'을(를) PDF에서 찾을 수 없습니다: {file_path}"

            return (
                f"## PDF 검색 결과\n\n"
                f"- 파일: {file_path}\n"
                f"- 검색어: {keyword}\n"
                f"- 발견 횟수: {len(findings)}건\n\n"
                + "\n".join(findings)
            )

        except Exception as e:
            return f"PDF 검색 중 오류 발생: {e}"

    @staticmethod
    def _parse_page_spec(spec: str) -> list[int]:
        """페이지 지정 문자열을 숫자 리스트로 변환. 예: '1-3,5' → [1,2,3,5]"""
        pages: list[int] = []
        for part in str(spec).split(","):
            part = part.strip()
            if "-" in part:
                start_s, end_s = part.split("-", 1)
                start, end = int(start_s.strip()), int(end_s.strip())
                pages.extend(range(start, end + 1))
            else:
                pages.append(int(part))
        return pages
