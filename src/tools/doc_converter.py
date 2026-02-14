"""
문서 변환 Tool.

pandoc을 사용하여 마크다운을 PDF, DOCX, ePub 등으로 변환합니다.

사용 방법:
  - action="to_pdf": 마크다운 → PDF
  - action="to_docx": 마크다운 → DOCX
  - action="to_epub": 마크다운 → ePub (전자책)

필요 환경변수: 없음 (pandoc 시스템 패키지 필요: apt install pandoc)
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.doc_converter")

OUTPUT_DIR = Path("output")


class DocConverterTool(BaseTool):
    """문서 변환 도구 (마크다운 → PDF/DOCX/ePub)."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "to_pdf")

        if action == "to_pdf":
            return await self._convert(kwargs, "pdf")
        elif action == "to_docx":
            return await self._convert(kwargs, "docx")
        elif action == "to_epub":
            return await self._convert(kwargs, "epub")
        else:
            return (
                f"알 수 없는 action: {action}. "
                "to_pdf, to_docx, to_epub 중 하나를 사용하세요."
            )

    async def _convert(self, kwargs: dict[str, Any], output_format: str) -> str:
        if not shutil.which("pandoc"):
            return (
                "pandoc이 설치되지 않았습니다.\n"
                "설치 방법:\n"
                "  Ubuntu/Debian: sudo apt install pandoc\n"
                "  macOS: brew install pandoc\n"
                "  Windows: choco install pandoc"
            )

        # 입력 소스 결정
        input_file = kwargs.get("input_file", "")
        content = kwargs.get("content", "")
        title = kwargs.get("title", "document")

        if not input_file and not content:
            return (
                "변환할 내용을 입력해주세요.\n"
                "  - input_file='path/to/file.md': 마크다운 파일 경로\n"
                "  - content='마크다운 텍스트': 직접 텍스트 입력"
            )

        # 출력 디렉토리 생성
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # 임시 입력 파일 생성 (content가 주어진 경우)
        temp_input = None
        if content and not input_file:
            temp_input = tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False, encoding="utf-8",
            )
            temp_input.write(content)
            temp_input.close()
            input_file = temp_input.name

        # 입력 파일 존재 확인
        if not os.path.exists(input_file):
            return f"입력 파일을 찾을 수 없습니다: {input_file}"

        # 출력 파일 경로
        safe_title = "".join(c for c in title if c.isalnum() or c in "-_ ").strip()
        output_file = OUTPUT_DIR / f"{safe_title}.{output_format}"

        # pandoc 명령어 구성
        cmd = ["pandoc", input_file, "-o", str(output_file)]

        if output_format == "pdf":
            # PDF는 LaTeX 엔진 필요
            if shutil.which("xelatex"):
                cmd.extend(["--pdf-engine=xelatex"])
                # 한글 폰트 설정 (있으면)
                cmd.extend(["-V", "mainfont=NanumGothic"])
            elif shutil.which("pdflatex"):
                cmd.extend(["--pdf-engine=pdflatex"])
            else:
                # LaTeX 없으면 HTML → PDF 시도
                cmd = [
                    "pandoc", input_file, "-o", str(output_file),
                    "--pdf-engine=wkhtmltopdf",
                ]
                if not shutil.which("wkhtmltopdf"):
                    # 임시 파일 정리
                    if temp_input:
                        os.unlink(temp_input.name)
                    return (
                        "PDF 변환에 필요한 엔진이 없습니다.\n"
                        "다음 중 하나를 설치하세요:\n"
                        "  sudo apt install texlive-xetex  (권장)\n"
                        "  sudo apt install wkhtmltopdf"
                    )

        elif output_format == "epub":
            # ePub 메타데이터
            author = kwargs.get("author", "CORTHEX HQ")
            cmd.extend(["--metadata", f"title={title}"])
            cmd.extend(["--metadata", f"author={author}"])

        # 변환 실행
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            if temp_input:
                os.unlink(temp_input.name)
            return "변환 타임아웃 (120초 초과)"
        finally:
            # 임시 파일 정리
            if temp_input and os.path.exists(temp_input.name):
                os.unlink(temp_input.name)

        if result.returncode != 0:
            error = result.stderr[:500]
            return f"변환 실패:\n{error}"

        if not output_file.exists():
            return "변환 결과 파일이 생성되지 않았습니다."

        size_kb = output_file.stat().st_size / 1024
        format_names = {"pdf": "PDF", "docx": "Word 문서", "epub": "전자책(ePub)"}

        return (
            f"문서 변환 완료!\n"
            f"  형식: {format_names.get(output_format, output_format)}\n"
            f"  파일: {output_file}\n"
            f"  크기: {size_kb:.1f} KB"
        )
