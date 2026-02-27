"""
정보국(knowledge/) 파일 조회 도구.

에이전트가 필요할 때만 knowledge/ 폴더의 지식 파일을 읽습니다.
매번 시스템 프롬프트에 주입하는 대신 on-demand 호출로 토큰 절약.

사용 방법:
  - division 없음                          → 전체 knowledge 폴더 목록
  - division="leet_master"                 → leet_master 폴더 파일 목록
  - division="leet_master", file="product_info" → product_info.md 전체 내용
"""
from __future__ import annotations

import logging
import os
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.read_knowledge")

# knowledge 폴더: 프로젝트 루트 기준
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KNOWLEDGE_DIR = os.path.join(_BASE_DIR, "knowledge")

_DIVISION_LABELS: dict[str, str] = {
    "leet_master": "리트마스터 — LEET 추리논증 AI 학습 플랫폼",
    "finance": "금융투자 정책/방침",
    "publishing": "출판·기록 가이드",
    "shared": "전사 공통 규칙",
    "flowcharts": "시스템 플로우차트",
}


class ReadKnowledgeTool(BaseTool):
    """정보국(knowledge/) 파일 on-demand 조회 도구."""

    async def execute(self, **kwargs: Any) -> str:
        division = kwargs.get("division", "").strip()
        file_name = kwargs.get("file", "").strip()

        if not division:
            return self._list_all()

        division_dir = os.path.join(KNOWLEDGE_DIR, division)
        if not os.path.isdir(division_dir):
            try:
                available = ", ".join(sorted(os.listdir(KNOWLEDGE_DIR)))
            except Exception:
                available = "(조회 실패)"
            return f"'{division}' division이 없습니다.\n사용 가능: {available}"

        if file_name:
            return self._read_file(division_dir, division, file_name)
        return self._list_division(division_dir, division)

    # ── 전체 목록 ──

    def _list_all(self) -> str:
        if not os.path.isdir(KNOWLEDGE_DIR):
            return f"knowledge 폴더가 없습니다: {KNOWLEDGE_DIR}"

        lines = ["## 정보국(knowledge) 전체 목록\n"]
        try:
            entries = sorted(os.listdir(KNOWLEDGE_DIR))
        except Exception as e:
            return f"폴더 읽기 실패: {e}"

        for d in entries:
            d_path = os.path.join(KNOWLEDGE_DIR, d)
            if not os.path.isdir(d_path):
                continue
            label = _DIVISION_LABELS.get(d, d)
            try:
                files = [f for f in os.listdir(d_path) if f.endswith(".md")]
            except Exception:
                files = []
            lines.append(f"**{d}** — {label} ({len(files)}개 파일)")
            for f in sorted(files):
                lines.append(f"  - {f[:-3]}")

        lines.append('\n사용법: division="leet_master", file="product_info" 형식으로 호출')
        return "\n".join(lines)

    # ── Division 내 파일 목록 ──

    def _list_division(self, division_dir: str, division: str) -> str:
        label = _DIVISION_LABELS.get(division, division)
        try:
            files = sorted([f for f in os.listdir(division_dir) if f.endswith(".md")])
        except Exception as e:
            return f"폴더 읽기 실패: {e}"

        if not files:
            return f"**{division}** 폴더에 파일이 없습니다."

        lines = [f"## 정보국 / {division} — {label}\n"]
        for f in files:
            path = os.path.join(division_dir, f)
            try:
                with open(path, "r", encoding="utf-8") as fp:
                    first_line = fp.readline().strip().lstrip("#").strip()
            except Exception:
                first_line = "(읽기 실패)"
            lines.append(f"**{f[:-3]}**: {first_line}")

        lines.append(f'\n전체 내용 조회: division="{division}", file="파일명"')
        return "\n".join(lines)

    # ── 파일 전체 내용 ──

    def _read_file(self, division_dir: str, division: str, file_name: str) -> str:
        if not file_name.endswith(".md"):
            file_name = file_name + ".md"

        path = os.path.join(division_dir, file_name)
        if not os.path.isfile(path):
            try:
                available = [f[:-3] for f in os.listdir(division_dir) if f.endswith(".md")]
            except Exception:
                available = []
            return (
                f"'{file_name}' 파일이 없습니다.\n"
                f"사용 가능: {', '.join(sorted(available))}"
            )

        try:
            with open(path, "r", encoding="utf-8") as fp:
                content = fp.read()
        except Exception as e:
            logger.error("[ReadKnowledge] 파일 읽기 실패 %s: %s", path, e)
            return f"파일 읽기 실패: {e}"

        label = _DIVISION_LABELS.get(division, division)
        header = f"## 정보국 / {division} / {file_name}\n> {label}\n\n"
        return header + content
