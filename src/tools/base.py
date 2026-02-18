"""Base tool interface for the CORTHEX HQ tool pool."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.llm.router import ModelRouter


class ToolConfig(BaseModel):
    """Configuration for a tool, loaded from tools.yaml."""

    tool_id: str
    name: str
    name_ko: str
    description: str
    model_name: str = "gpt-5-mini"


class BaseTool(ABC):
    """Abstract base for all tools in the CORTHEX HQ tool pool."""

    def __init__(self, config: ToolConfig, model_router: ModelRouter) -> None:
        self.config = config
        self.model_router = model_router

    @property
    def tool_id(self) -> str:
        return self.config.tool_id

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Run the tool with given inputs."""
        ...

    async def _llm_call(
        self,
        system_prompt: str,
        user_prompt: str,
        caller_model: str | None = None,
    ) -> str:
        """Make an LLM call powered by this tool's assigned model.

        caller_model이 있으면 해당 모델을 우선 사용하고,
        없으면 tools.yaml에 설정된 model_name으로 폴백합니다.
        model_router가 지원하지 않는 모델(Gemini 등)이면 config 기본값으로 폴백합니다.
        """
        # model_router는 gpt-*/o*-*/claude-*/gemini-* 지원
        _SUPPORTED_PREFIXES = ("gpt-", "o1-", "o3-", "o4-", "o5-", "claude-", "gemini-")
        _is_supported = caller_model and any(caller_model.startswith(p) for p in _SUPPORTED_PREFIXES)
        model = (caller_model if _is_supported else None) or self.config.model_name or "claude-sonnet-4-6"
        response = await self.model_router.complete(
            model_name=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=1.0,
        )
        return response.content
