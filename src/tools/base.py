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

    async def _llm_call(self, system_prompt: str, user_prompt: str) -> str:
        """Make an LLM call powered by this tool's assigned model."""
        response = await self.model_router.complete(
            model_name=self.config.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return response.content
