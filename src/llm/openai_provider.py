"""OpenAI LLM provider implementation."""
from __future__ import annotations

import logging
from typing import Optional

from openai import AsyncOpenAI

from src.llm.base import LLMProvider, LLMResponse

logger = logging.getLogger("corthex.llm.openai")

# Cost per 1M tokens (input / output)
_PRICING: dict[str, dict[str, float]] = {
    # GPT-4o 시리즈
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    # GPT-5 시리즈
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
    "gpt-5": {"input": 1.25, "output": 10.00},
    "gpt-5-2": {"input": 1.75, "output": 14.00},
    "gpt-5-2-pro": {"input": 21.00, "output": 168.00},
}


class OpenAIProvider(LLMProvider):
    """OpenAI API provider using AsyncOpenAI."""

    def __init__(self, api_key: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
        is_batch: bool = False,
    ) -> LLMResponse:
        logger.debug("OpenAI 호출: model=%s, msgs=%d", model, len(messages))

        kwargs: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # reasoning_effort 지원 (GPT-5.2, o-시리즈 등)
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort

        resp = await self._client.chat.completions.create(**kwargs)

        if not resp.choices:
            raise RuntimeError(f"OpenAI 응답에 choices가 비어있습니다 (model={model})")
        choice = resp.choices[0]
        usage = resp.usage
        content = choice.message.content or ""
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        cost = self._calculate_cost(model, input_tokens, output_tokens, is_batch)

        logger.debug(
            "OpenAI 응답: tokens=%d+%d, cost=$%.6f%s",
            input_tokens, output_tokens, cost,
            " (batch)" if is_batch else "",
        )

        return LLMResponse(
            content=content,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            provider="openai",
        )

    async def close(self) -> None:
        await self._client.close()

    @staticmethod
    def _calculate_cost(
        model: str, input_tokens: int, output_tokens: int, is_batch: bool = False,
    ) -> float:
        pricing = _PRICING.get(model, {"input": 0.0, "output": 0.0})
        cost = (
            input_tokens * pricing["input"] + output_tokens * pricing["output"]
        ) / 1_000_000
        # Batch API = 50% 할인
        if is_batch:
            cost *= 0.5
        return cost
