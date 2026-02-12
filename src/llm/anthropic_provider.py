"""Anthropic LLM provider implementation."""
from __future__ import annotations

import logging

from anthropic import AsyncAnthropic

from src.llm.base import LLMProvider, LLMResponse

logger = logging.getLogger("corthex.llm.anthropic")

# Cost per 1M tokens (input / output)
_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-opus-4-0-20250514": {"input": 15.00, "output": 75.00},
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

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": api_messages,
            "temperature": temperature,
        }
        if system_msg:
            kwargs["system"] = system_msg

        resp = await self._client.messages.create(**kwargs)

        content = resp.content[0].text if resp.content else ""
        input_tokens = resp.usage.input_tokens
        output_tokens = resp.usage.output_tokens
        cost = self._calculate_cost(model, input_tokens, output_tokens)

        logger.debug(
            "Anthropic 응답: tokens=%d+%d, cost=$%.6f",
            input_tokens, output_tokens, cost,
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
    def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = _PRICING.get(model, {"input": 0.0, "output": 0.0})
        return (
            input_tokens * pricing["input"] + output_tokens * pricing["output"]
        ) / 1_000_000
