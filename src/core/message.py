"""
Message types for inter-agent communication.

All agents in CORTHEX HQ communicate through structured messages.
This is the nervous system of the entire organization.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict


class MessageType(str, Enum):
    TASK_REQUEST = "task_request"
    TASK_RESULT = "task_result"
    STATUS_UPDATE = "status_update"
    TOOL_REQUEST = "tool_request"
    TOOL_RESULT = "tool_result"
    BROADCAST = "broadcast"
    ERROR = "error"


class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Message(BaseModel):
    """Base message for all inter-agent communication."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=_new_id)
    type: MessageType
    sender_id: str
    receiver_id: str
    timestamp: datetime = Field(default_factory=_now)
    priority: Priority = Priority.NORMAL
    payload: dict[str, Any] = Field(default_factory=dict)
    parent_message_id: Optional[str] = None
    correlation_id: str = Field(default_factory=_new_id)


class TaskRequest(Message):
    """A specific task delegated from a superior to a subordinate."""

    type: MessageType = MessageType.TASK_REQUEST
    task_description: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    expected_output_format: Optional[str] = None


class TaskResult(Message):
    """Result returned from a subordinate to the delegating agent."""

    type: MessageType = MessageType.TASK_RESULT
    success: bool = True
    result_data: Any = None
    summary: str = ""
    tokens_used: int = 0
    cost_usd: float = 0.0
    execution_time_seconds: float = 0.0


class StatusUpdate(Message):
    """Progress update from any agent during long-running tasks."""

    type: MessageType = MessageType.STATUS_UPDATE
    progress_pct: float = 0.0
    current_step: str = ""
    detail: str = ""
