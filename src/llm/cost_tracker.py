"""Token usage and cost tracking across all LLM calls."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from src.llm.base import LLMResponse


@dataclass
class CostRecord:
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class CostTracker:
    """Accumulates token usage and cost across all LLM calls in a session."""

    def __init__(self) -> None:
        self._records: list[CostRecord] = []

    def record(self, response: LLMResponse) -> None:
        self._records.append(CostRecord(
            model=response.model,
            provider=response.provider,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=response.cost_usd,
        ))

    @property
    def total_cost(self) -> float:
        return sum(r.cost_usd for r in self._records)

    @property
    def total_tokens(self) -> int:
        return sum(r.input_tokens + r.output_tokens for r in self._records)

    @property
    def total_calls(self) -> int:
        return len(self._records)

    def summary_by_model(self) -> dict[str, dict]:
        """Group costs by model for the CEO dashboard."""
        summary: dict[str, dict] = defaultdict(
            lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
        )
        for r in self._records:
            s = summary[r.model]
            s["calls"] += 1
            s["input_tokens"] += r.input_tokens
            s["output_tokens"] += r.output_tokens
            s["cost_usd"] += r.cost_usd
        return dict(summary)

    def reset(self) -> None:
        self._records.clear()
