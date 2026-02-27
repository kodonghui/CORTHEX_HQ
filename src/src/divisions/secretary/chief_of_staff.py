"""
비서실장 (Chief of Staff) - Manager Agent

CEO에게 올라가는 보고를 요약하고, 일정/미결을 추적하며,
사업부 간 정보를 중계합니다.
"""
from __future__ import annotations

from src.core.agent import ManagerAgent, AgentConfig
from src.core.message import TaskRequest

from typing import Any


class ChiefOfStaffAgent(ManagerAgent):
    """비서실장: 보고 요약, 일정 추적, 정보 중계를 총괄."""

    async def execute(self, request: TaskRequest) -> Any:
        # 비서실은 항상 3개 Worker를 병렬로 활용
        return await super().execute(request)
