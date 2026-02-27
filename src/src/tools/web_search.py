"""웹검색 Tool: 간이 웹 검색 (LLM 지식 기반)."""
from __future__ import annotations
from typing import Any
from src.tools.base import BaseTool


class WebSearchTool(BaseTool):
    """실시간 웹 검색 시뮬레이션 (LLM 지식 기반 답변)."""

    async def execute(self, query: str = "", **kwargs: Any) -> str:
        return await self._llm_call(
            system_prompt=(
                "당신은 리서치 어시스턴트입니다. 주어진 질문에 대해 "
                "가능한 한 최신 정보를 바탕으로 상세하게 답변하세요.\n"
                "출처가 불확실한 정보는 '확인 필요'로 표시하세요.\n"
                "수치 데이터는 대략적인 범위로 제시하세요."
            ),
            user_prompt=query,
        )
