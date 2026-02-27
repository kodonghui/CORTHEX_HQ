"""Google Gemini LLM provider implementation."""
from __future__ import annotations

import asyncio
import logging

from src.llm.base import LLMProvider, LLMResponse

logger = logging.getLogger("corthex.llm.gemini")

# Cost per 1M tokens (input / output)
_PRICING: dict[str, dict[str, float]] = {
    "gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
}


class GeminiProvider(LLMProvider):
    """Google Gemini API provider using google-genai SDK."""

    def __init__(self, api_key: str) -> None:
        from google import genai  # type: ignore
        self._client = genai.Client(api_key=api_key)

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
        is_batch: bool = False,
    ) -> LLMResponse:
        logger.debug("Gemini 호출: model=%s, msgs=%d", model, len(messages))

        # Extract system prompt and user message
        system_instruction = ""
        user_parts: list[str] = []
        for m in messages:
            if m["role"] == "system":
                system_instruction = m["content"]
            else:
                user_parts.append(m["content"])

        contents = " ".join(user_parts) if user_parts else "(no input)"

        # Build generation config
        config: dict = {
            "max_output_tokens": max_tokens,
            "temperature": 1.0 if reasoning_effort else temperature,
        }
        if system_instruction:
            config["system_instruction"] = system_instruction

        # google-genai SDK는 동기 API → asyncio.to_thread로 비동기 실행
        def _sync_call() -> object:
            return self._client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )

        resp = await asyncio.to_thread(_sync_call)

        # Extract text content
        content = ""
        if (
            resp.candidates
            and resp.candidates[0].content
            and resp.candidates[0].content.parts
        ):
            for part in resp.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    content = part.text
                    break

        usage = getattr(resp, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
        cost = self._calculate_cost(model, input_tokens, output_tokens)

        logger.debug(
            "Gemini 응답: tokens=%d+%d, cost=$%.6f",
            input_tokens, output_tokens, cost,
        )

        return LLMResponse(
            content=content,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            provider="google",
        )

    async def close(self) -> None:
        pass  # google-genai SDK는 별도 정리 불필요

    @staticmethod
    def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = _PRICING.get(model, {"input": 0.0, "output": 0.0})
        return (
            input_tokens * pricing["input"] + output_tokens * pricing["output"]
        ) / 1_000_000
