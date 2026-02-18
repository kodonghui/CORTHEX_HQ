"""
Generic Skill Tool: AI 기반 범용 스킬 도구.

config/tools.yaml의 description 필드를 기반으로 자동 시스템 프롬프트를 생성합니다.
89개 Skill 도구 (마케팅, 개발, 코딩 패턴, 유틸리티 등)가 이 클래스를 공유합니다.
"""
from __future__ import annotations

from typing import Any

from src.tools.base import BaseTool


class SkillTool(BaseTool):
    """AI LLM을 활용하는 범용 스킬 도구.

    tools.yaml의 name_ko + description으로 전문가 역할이 자동 설정됩니다.
    """

    async def execute(self, prompt: str = "", **kwargs: Any) -> str:
        system_prompt = (
            f"당신은 '{self.config.name_ko}' 전문가입니다.\n"
            f"전문 분야: {self.config.description}\n\n"
            "## 응답 규칙\n"
            "- 한국어로 답변하세요.\n"
            "- 구체적이고 실행 가능한 조언을 제공하세요.\n"
            "- 필요하면 코드, 예시, 체크리스트를 포함하세요.\n"
            "- 전문 용어를 쓸 때는 괄호 안에 쉬운 설명을 붙이세요.\n"
            "- 마크다운으로 구조화하여 답변하세요."
        )
        return await self._llm_call(
            system_prompt=system_prompt,
            user_prompt=prompt or kwargs.get("input", "도움을 요청합니다."),
            caller_model=kwargs.get("_caller_model"),
        )
