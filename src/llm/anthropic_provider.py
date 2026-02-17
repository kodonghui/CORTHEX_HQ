"""Anthropic LLM provider implementation."""
from __future__ import annotations

import logging

from anthropic import AsyncAnthropic

from src.llm.base import LLMProvider, LLMResponse

logger = logging.getLogger("corthex.llm.anthropic")

# Cost per 1M tokens (input / output)
_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-6": {"input": 5.00, "output": 25.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
    "claude-opus-4-0-20250514": {"input": 15.00, "output": 75.00},
}

# Extended thinking budget per reasoning effort level
_THINKING_BUDGET: dict[str, int] = {
    "low": 2048,
    "medium": 8192,
    "high": 32768,
}


class AnthropicProvider(LLMProvider):
    """Anthropic API provider using AsyncAnthropic."""

    def __init__(self, api_key: str) -> None:
        self._client = AsyncAnthropic(api_key=api_key)

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
        is_batch: bool = False,
    ) -> LLMResponse:
        logger.debug("Anthropic 호출: model=%s, msgs=%d", model, len(messages))

        # Anthropic uses a separate 'system' parameter
        system_msg = ""
        api_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                api_messages.append({"role": m["role"], "content": m["content"]})

        # Ensure at least one user message
        if not api_messages:
            api_messages = [{"role": "user", "content": "(no input)"}]

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": api_messages,
        }
        if system_msg:
            kwargs["system"] = system_msg

        # Extended thinking 지원
        if reasoning_effort and reasoning_effort in _THINKING_BUDGET:
            budget = _THINKING_BUDGET[reasoning_effort]
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
            # thinking 모드에서는 temperature 사용 불가
        else:
            kwargs["temperature"] = temperature

        resp = await self._client.messages.create(**kwargs)

        # thinking 응답에서 텍스트 블록만 추출
        content = ""
        for block in resp.content:
            if block.type == "text":
                content = block.text
                break

        input_tokens = resp.usage.input_tokens
        output_tokens = resp.usage.output_tokens
        cost = self._calculate_cost(model, input_tokens, output_tokens, is_batch)

        logger.debug(
            "Anthropic 응답: tokens=%d+%d, cost=$%.6f%s",
            input_tokens, output_tokens, cost,
            " (batch)" if is_batch else "",
        )

        return LLMResponse(
            content=content,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            provider="anthropic",
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
