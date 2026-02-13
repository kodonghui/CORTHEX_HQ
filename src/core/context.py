"""
Shared context accessible to all agents.

Provides:
- Registry reference (so managers can look up subordinates)
- Conversation history per correlation_id
- Cross-division bulletin board
- Status callback for CLI live updates
"""
from __future__ import annotations

from typing import Any, Callable, Optional, TYPE_CHECKING

from src.core.message import Message

if TYPE_CHECKING:
    from src.core.registry import AgentRegistry
    from src.core.quality_gate import QualityGate


class SharedContext:
    """Global shared state for the entire CORTHEX HQ system."""

    def __init__(self) -> None:
        self.registry: Optional[AgentRegistry] = None
        self.quality_gate: Optional[QualityGate] = None
        self._conversations: dict[str, list[Message]] = {}
        self._bulletin: list[Message] = []
        self._status_callback: Optional[Callable[[Message], Any]] = None

    def set_registry(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def set_quality_gate(self, gate: QualityGate) -> None:
        self.quality_gate = gate

    def set_status_callback(self, callback: Callable[[Message], Any]) -> None:
        self._status_callback = callback

    def log_message(self, msg: Message) -> None:
        cid = msg.correlation_id
        if cid not in self._conversations:
            self._conversations[cid] = []
        self._conversations[cid].append(msg)
        if self._status_callback:
            self._status_callback(msg)

    def post_bulletin(self, msg: Message) -> None:
        self._bulletin.append(msg)

    def get_conversation(self, correlation_id: str) -> list[Message]:
        return self._conversations.get(correlation_id, [])

    def get_recent_bulletins(self, limit: int = 10) -> list[Message]:
        return self._bulletin[-limit:]
