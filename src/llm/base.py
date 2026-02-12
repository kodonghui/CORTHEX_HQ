"""Base LLM provider interface and unified response model."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class LLMResponse:
    """Unified response from any LLM provider."""

    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    provider: str  # "openai" or "anthropic"


class LLMProvider(ABC):
    """Abstract base for LLM provider implementations."""

    @abstractmethod
    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up HTTP clients."""
        ...
