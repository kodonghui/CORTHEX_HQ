"""변리사 Tool: 특허/IP 분석."""
from __future__ import annotations
from typing import Any
from src.tools.base import BaseTool


class PatentAttorneyTool(BaseTool):
    """특허 출원, 선행기술 조사, 특허 침해 분석."""

    _PROMPTS = {
        "patentability": (
            "당신은 대한민국 변리사입니다. 주어진 기술/아이디어의 특허 가능성을 분석하세요.\n"
            "1) 신규성 2) 진보성 3) 산업상 이용가능성 관점에서 평가하세요.\n"
            "선행기술 가능성도 언급하세요."
        ),
        "infringement": (
            "당신은 대한민국 변리사입니다. 주어진 기술/제품이 기존 특허를 침해할 가능성을 분석하세요.\n"
            "침해 유형(직접침해, 간접침해)과 회피 설계 방안을 제안하세요."
        ),
        "prior_art": (
            "당신은 대한민국 변리사입니다. 주어진 기술에 대한 선행기술 조사를 수행하세요.\n"
            "관련 가능한 기존 특허/논문/기술을 식별하고, 차별점을 분석하세요."
        ),
    }

    async def execute(self, query: str = "", analysis_type: str = "patentability", **kwargs: Any) -> str:
        system_prompt = self._PROMPTS.get(analysis_type, self._PROMPTS["patentability"])
        return await self._llm_call(system_prompt, query)
