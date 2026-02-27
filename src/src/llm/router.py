"""
Model Router: single point of contact for all LLM calls.

Routes to the correct provider (OpenAI / Anthropic / Google) based on model name prefix.
Also accumulates cost tracking.
"""
from __future__ import annotations

import logging
from typing import Optional

from src.llm.base import LLMProvider, LLMResponse
from src.llm.cost_tracker import CostTracker

logger = logging.getLogger("corthex.llm.router")


class ModelRouter:
    """
    Routes model requests to the correct provider.

    Model name prefix determines provider:
      gpt-*, o3-*, o1-*, o4-*, o5-*  -> OpenAI
      claude-*                         -> Anthropic
      gemini-*                         -> Google
    """

    def __init__(
        self,
        openai_provider: Optional[LLMProvider] = None,
        anthropic_provider: Optional[LLMProvider] = None,
        google_provider: Optional[LLMProvider] = None,
    ) -> None:
        self._providers: dict[str, LLMProvider] = {}
        if openai_provider:
            self._providers["openai"] = openai_provider
        if anthropic_provider:
            self._providers["anthropic"] = anthropic_provider
        if google_provider:
            self._providers["google"] = google_provider
        self.cost_tracker = CostTracker()
        self.batch_collector = None  # BatchCollector 주입 시 사용

    def _resolve_provider(self, model_name: str) -> LLMProvider:
        if model_name.startswith(("gpt-", "o3-", "o1-", "o4-", "o5-")):
            provider = self._providers.get("openai")
            if not provider:
                raise ValueError("OpenAI provider가 설정되지 않았습니다. OPENAI_API_KEY를 확인하세요.")
            return provider
        elif model_name.startswith("claude-"):
            provider = self._providers.get("anthropic")
            if not provider:
                raise ValueError("Anthropic provider가 설정되지 않았습니다. ANTHROPIC_API_KEY를 확인하세요.")
            return provider
        elif model_name.startswith("gemini-"):
            provider = self._providers.get("google")
            if not provider:
                raise ValueError("Google provider가 설정되지 않았습니다. GOOGLE_API_KEY를 확인하세요.")
            return provider
        else:
            raise ValueError(f"알 수 없는 모델: {model_name}")

    async def complete(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        agent_id: str = "",
        reasoning_effort: str | None = None,
        use_batch: bool = False,
    ) -> LLMResponse:
        """Route a completion request to the appropriate provider."""
        # Batch 모드: BatchCollector가 있으면 위임
        if use_batch and self.batch_collector:
            response = await self.batch_collector.submit(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
            )
        else:
            # 실시간 모드
            provider = self._resolve_provider(model_name)
            response = await provider.complete(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
                is_batch=False,
            )
        self.cost_tracker.record(response, agent_id=agent_id)
        return response

    async def close(self) -> None:
        """Close all provider connections."""
        for provider in self._providers.values():
            await provider.close()
