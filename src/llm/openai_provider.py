"""OpenAI LLM provider implementation."""
from __future__ import annotations

import logging
from typing import Optional

from openai import AsyncOpenAI

from src.llm.base import LLMProvider, LLMResponse

logger = logging.getLogger("corthex.llm.openai")

# Cost per 1M tokens (input / output)
_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "o3-mini": {"input": 1.10, "output": 4.40},
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
    ) -> LLMResponse:
        logger.debug("OpenAI 호출: model=%s, msgs=%d", model, len(messages))

        resp = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        choice = resp.choices[0]
        usage = resp.usage
        content = choice.message.content or ""
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        cost = self._calculate_cost(model, input_tokens, output_tokens)

        logger.debug(
            "OpenAI 응답: tokens=%d+%d, cost=$%.6f",
            input_tokens, output_tokens, cost,
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
    def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = _PRICING.get(model, {"input": 0.0, "output": 0.0})
        return (
            input_tokens * pricing["input"] + output_tokens * pricing["output"]
        ) / 1_000_000
