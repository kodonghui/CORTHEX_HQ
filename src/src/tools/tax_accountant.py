"""세무사 Tool: 세무 관련 조언."""
from __future__ import annotations
from typing import Any
from src.tools.base import BaseTool


class TaxAccountantTool(BaseTool):
    """세무 관련 조언, 절세 전략, 세금 계산."""

    async def execute(self, query: str = "", **kwargs: Any) -> str:
        return await self._llm_call(
            system_prompt=(
                "당신은 대한민국 세무사입니다. 세무 관련 질문에 정확하게 답변하세요.\n"
                "관련 세법 조항을 인용하고, 절세 방안이 있다면 제안하세요.\n"
                "주의: 이것은 참고용이며, 실제 세무 신고 시 공인 세무사와 상담을 권장합니다."
            ),
            user_prompt=query,
        )
