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
    model_name: str = ""


class BaseTool(ABC):
    """Abstract base for all tools in the CORTHEX HQ tool pool."""

    def __init__(self, config: ToolConfig, model_router: ModelRouter) -> None:
        self.config = config
        self.model_router = model_router
        # pool.invoke()가 호출 전에 설정 — 모든 도구가 자동으로 에이전트 모델/temp 사용
        self._current_caller_model: str | None = None
        self._current_caller_temperature: float | None = None

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
        caller_temperature: float | None = None,
    ) -> str:
        """Make an LLM call — 호출한 에이전트의 모델/temperature를 자동으로 사용합니다.

        우선순위(모델): 명시적 caller_model → 인스턴스 _current_caller_model → gpt-5-mini
        우선순위(temp): 명시적 caller_temperature → 인스턴스 _current_caller_temperature → 0.7
        도구가 직접 _llm_call(caller_model=...) 안 넘겨도 pool.invoke에서 자동 설정됨.
        """
        _SUPPORTED_PREFIXES = ("gpt-", "o1-", "o3-", "o4-", "o5-", "claude-", "gemini-")
        # 명시적 파라미터 → 인스턴스 변수(pool.invoke가 설정) → 폴백
        _model = caller_model or self._current_caller_model
        _is_supported = _model and any(_model.startswith(p) for p in _SUPPORTED_PREFIXES)
        model = (_model if _is_supported else None) or "gpt-5-mini"
        temp = caller_temperature if caller_temperature is not None else (
            self._current_caller_temperature if self._current_caller_temperature is not None else 0.7
        )
        response = await self.model_router.complete(
            model_name=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temp,
        )
        return response.content
