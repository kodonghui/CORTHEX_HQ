"""
Agent Performance Dashboard for CORTHEX HQ.

Aggregates per-agent statistics from CostTracker and SharedContext:
- LLM call count, token usage, cost
- Average response time
- Success / failure rate
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.context import SharedContext
    from src.llm.cost_tracker import CostTracker

from src.core.message import MessageType


@dataclass
class AgentStats:
    agent_id: str
    name_ko: str = ""
    role: str = ""
    model_name: str = ""
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    tasks_received: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_execution_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        total = self.tasks_completed + self.tasks_failed
        if total == 0:
            return 0.0
        return self.tasks_completed / total * 100

    @property
    def avg_execution_seconds(self) -> float:
        if self.tasks_completed == 0:
            return 0.0
        return self.total_execution_seconds / self.tasks_completed

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name_ko": self.name_ko,
            "role": self.role,
            "model_name": self.model_name,
            "llm_calls": self.llm_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "tasks_received": self.tasks_received,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "success_rate": round(self.success_rate, 1),
            "avg_execution_seconds": round(self.avg_execution_seconds, 2),
            "total_execution_seconds": round(self.total_execution_seconds, 2),
        }


@dataclass
class PerformanceReport:
    agents: list[AgentStats] = field(default_factory=list)
    total_llm_calls: int = 0
    total_cost_usd: float = 0.0
    total_tasks: int = 0

    def to_dict(self) -> dict:
        return {
            "total_llm_calls": self.total_llm_calls,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_tasks": self.total_tasks,
            "agents": [a.to_dict() for a in self.agents],
        }


def build_performance_report(
    cost_tracker: CostTracker,
    context: SharedContext,
) -> PerformanceReport:
    """Build a consolidated performance report from all available data."""
    from src.core.registry import AgentRegistry

    registry = context.registry
    if not registry:
        return PerformanceReport()

    # Initialize stats for all agents
    stats_map: dict[str, AgentStats] = {}
    for agent in registry.list_all():
        cfg = agent.config
        stats_map[cfg.agent_id] = AgentStats(
            agent_id=cfg.agent_id,
            name_ko=cfg.name_ko,
            role=cfg.role,
            model_name=cfg.model_name,
        )

    # Aggregate LLM cost data
    cost_by_agent = cost_tracker.summary_by_agent()
    for agent_id, data in cost_by_agent.items():
        if agent_id in stats_map:
            s = stats_map[agent_id]
            s.llm_calls = data["calls"]
            s.input_tokens = data["input_tokens"]
            s.output_tokens = data["output_tokens"]
            s.cost_usd = data["cost_usd"]

    # Aggregate task results from conversation history
    for conv_messages in context._conversations.values():
        for msg in conv_messages:
            if msg.type == MessageType.TASK_REQUEST:
                receiver = msg.receiver_id
                if receiver in stats_map:
                    stats_map[receiver].tasks_received += 1
            elif msg.type == MessageType.TASK_RESULT:
                sender = msg.sender_id
                if sender in stats_map:
                    if msg.success:
                        stats_map[sender].tasks_completed += 1
                        stats_map[sender].total_execution_seconds += (
                            msg.execution_time_seconds or 0.0
                        )
                    else:
                        stats_map[sender].tasks_failed += 1

    # Build report
    agents = sorted(
        stats_map.values(),
        key=lambda s: s.cost_usd,
        reverse=True,
    )

    return PerformanceReport(
        agents=agents,
        total_llm_calls=cost_tracker.total_calls,
        total_cost_usd=cost_tracker.total_cost,
        total_tasks=sum(a.tasks_received for a in agents),
    )
