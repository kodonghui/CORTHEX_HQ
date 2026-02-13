"""
In-memory task store for background task execution.

Tasks survive browser disconnect but not server restart.
For a solo developer running locally, this is the right tradeoff.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StoredTask:
    """A task tracked in the store."""

    task_id: str
    command: str
    status: TaskStatus = TaskStatus.QUEUED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_data: Optional[str] = None
    result_summary: Optional[str] = None
    success: Optional[bool] = None
    cost_usd: float = 0.0
    tokens_used: int = 0
    execution_time_seconds: float = 0.0
    output_file: Optional[str] = None


class TaskStore:
    """In-memory store for background tasks."""

    def __init__(self) -> None:
        self._tasks: dict[str, StoredTask] = {}

    def create(self, command: str) -> StoredTask:
        task_id = str(uuid.uuid4())[:8]
        task = StoredTask(task_id=task_id, command=command)
        self._tasks[task_id] = task
        return task

    def get(self, task_id: str) -> Optional[StoredTask]:
        return self._tasks.get(task_id)

    def list_all(self, limit: int = 50) -> list[StoredTask]:
        return sorted(
            self._tasks.values(),
            key=lambda t: t.created_at,
            reverse=True,
        )[:limit]

    def list_running(self) -> list[StoredTask]:
        return [t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]
