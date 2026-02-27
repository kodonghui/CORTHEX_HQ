"""
Agent Collaboration Replay for CORTHEX HQ.

Reconstructs the delegation tree from a completed task's message history.
Shows who delegated what to whom, and how results were synthesized.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from src.core.message import Message, MessageType

if TYPE_CHECKING:
    from src.core.context import SharedContext
    from src.core.registry import AgentRegistry


@dataclass
class ReplayNode:
    """A single node in the delegation tree."""
    agent_id: str
    agent_name: str  # name_ko
    role: str
    task_description: str = ""
    result_summary: str = ""
    success: bool = True
    execution_time: float = 0.0
    children: list[ReplayNode] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "role": self.role,
            "task_description": self.task_description,
            "result_summary": self.result_summary,
            "success": self.success,
            "execution_time": round(self.execution_time, 2),
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class ReplayReport:
    """Full replay of a task's delegation flow."""
    correlation_id: str
    root: Optional[ReplayNode] = None
    total_agents_involved: int = 0
    total_execution_time: float = 0.0

    def to_dict(self) -> dict:
        return {
            "correlation_id": self.correlation_id,
            "root": self.root.to_dict() if self.root else None,
            "total_agents_involved": self.total_agents_involved,
            "total_execution_time": round(self.total_execution_time, 2),
        }


def build_replay(
    correlation_id: str,
    context: SharedContext,
) -> Optional[ReplayReport]:
    """Build a replay tree from the message history of a given correlation_id."""
    messages = context.get_conversation(correlation_id)
    if not messages:
        return None

    registry = context.registry

    def _agent_name(agent_id: str) -> str:
        if agent_id == "ceo":
            return "CEO"
        if registry:
            try:
                return registry.get_agent(agent_id).config.name_ko
            except Exception:
                pass
        return agent_id

    def _agent_role(agent_id: str) -> str:
        if agent_id == "ceo":
            return "ceo"
        if registry:
            try:
                return registry.get_agent(agent_id).config.role
            except Exception:
                pass
        return ""

    # Collect requests and results by receiver/sender
    requests: dict[str, Message] = {}  # message_id -> TaskRequest
    results_by_parent: dict[str, Message] = {}  # parent_message_id -> TaskResult

    for msg in messages:
        if msg.type == MessageType.TASK_REQUEST:
            requests[msg.id] = msg
        elif msg.type == MessageType.TASK_RESULT:
            if msg.parent_message_id:
                results_by_parent[msg.parent_message_id] = msg

    # Build tree recursively
    agent_set: set[str] = set()

    def _build_node(request_msg: Message) -> ReplayNode:
        receiver = request_msg.receiver_id
        agent_set.add(receiver)

        result_msg = results_by_parent.get(request_msg.id)

        node = ReplayNode(
            agent_id=receiver,
            agent_name=_agent_name(receiver),
            role=_agent_role(receiver),
            task_description=getattr(request_msg, "task_description", ""),
            result_summary=getattr(result_msg, "summary", "") if result_msg else "",
            success=getattr(result_msg, "success", True) if result_msg else True,
            execution_time=getattr(result_msg, "execution_time_seconds", 0.0) if result_msg else 0.0,
        )

        # Find child requests (requests sent BY this receiver)
        for msg in messages:
            if (
                msg.type == MessageType.TASK_REQUEST
                and msg.sender_id == receiver
                and msg.id != request_msg.id
            ):
                child = _build_node(msg)
                node.children.append(child)

        return node

    # Find the root request (from CEO)
    root_request = None
    for msg in messages:
        if msg.type == MessageType.TASK_REQUEST and msg.sender_id == "ceo":
            root_request = msg
            break

    if not root_request:
        return None

    root_node = _build_node(root_request)
    root_result = results_by_parent.get(root_request.id)
    total_time = getattr(root_result, "execution_time_seconds", 0.0) if root_result else 0.0

    return ReplayReport(
        correlation_id=correlation_id,
        root=root_node,
        total_agents_involved=len(agent_set),
        total_execution_time=total_time,
    )


def get_last_correlation_id(context: SharedContext) -> Optional[str]:
    """Get the most recent correlation_id from context."""
    if not context._conversations:
        return None
    # Return the last key (most recently added)
    return list(context._conversations.keys())[-1]
