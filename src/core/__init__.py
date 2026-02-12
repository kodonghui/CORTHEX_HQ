"""Core agent framework for CORTHEX HQ."""
from src.core.message import Message, TaskRequest, TaskResult, StatusUpdate, MessageType, Priority
from src.core.agent import AgentConfig, BaseAgent, ManagerAgent, SpecialistAgent, WorkerAgent
from src.core.context import SharedContext
from src.core.registry import AgentRegistry
from src.core.orchestrator import Orchestrator

__all__ = [
    "Message", "TaskRequest", "TaskResult", "StatusUpdate", "MessageType", "Priority",
    "AgentConfig", "BaseAgent", "ManagerAgent", "SpecialistAgent", "WorkerAgent",
    "SharedContext", "AgentRegistry", "Orchestrator",
]
