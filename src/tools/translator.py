"""번역가 Tool: 다국어 번역."""
from __future__ import annotations
from typing import Any
from src.tools.base import BaseTool


class TranslatorTool(BaseTool):
    """한영/영한 번역, 기술 문서 번역."""

    async def execute(
        self,
        text: str = "",
        source_lang: str = "auto",
        target_lang: str = "ko",
        **kwargs: Any,
    ) -> str:
        return await self._llm_call(
            system_prompt=(
                f"당신은 전문 번역가입니다. {source_lang}에서 {target_lang}로 번역하세요.\n"
                "원문의 톤과 기술적 정확성을 유지하세요.\n"
                "전문 용어는 괄호 안에 원문을 병기하세요."
            ),
            user_prompt=text,
        )
