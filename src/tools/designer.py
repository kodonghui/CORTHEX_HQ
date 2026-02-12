"""디자이너 Tool: UI/UX 디자인 조언."""
from __future__ import annotations
from typing import Any
from src.tools.base import BaseTool


class DesignerTool(BaseTool):
    """UI/UX 디자인 조언, 디자인 시스템, 와이어프레임 설명."""

    async def execute(self, prompt: str = "", **kwargs: Any) -> str:
        return await self._llm_call(
            system_prompt=(
                "당신은 시니어 UI/UX 디자이너입니다.\n"
                "디자인 원칙(접근성, 일관성, 사용성)에 기반하여 조언하세요.\n"
                "와이어프레임은 ASCII 아트로, 색상은 HEX 코드로 제안하세요.\n"
                "모바일 퍼스트 반응형 디자인을 우선하세요."
            ),
            user_prompt=prompt,
        )
