"""
금융분석팀장 (CIO Manager)

핵심 로직: 시황/종목/기술적 분석을 병렬 실행한 뒤,
그 결과를 리스크관리 전문가에게 순차적으로 넘겨 최종 판단을 합성합니다.
"""
from __future__ import annotations

import asyncio
from typing import Any

from src.core.agent import ManagerAgent
from src.core.message import TaskRequest, TaskResult


class CIOManagerAgent(ManagerAgent):
    """
    금융분석팀장 (CIO).

    Phase 1: 시황분석 + 종목분석 + 기술적분석 → 병렬 실행
    Phase 2: 위 결과 → 리스크관리 전문가 → 순차 실행
    Phase 3: 전체 결과 종합
    """

    PARALLEL_AGENT_IDS = [
        "market_condition_specialist",
        "stock_analysis_specialist",
        "technical_analysis_specialist",
    ]
    RISK_AGENT_ID = "risk_management_specialist"

    async def execute(self, request: TaskRequest) -> Any:
        # Phase 1: Parallel analysis
        parallel_tasks = []
        for agent_id in self.PARALLEL_AGENT_IDS:
            try:
                agent = self.context.registry.get_agent(agent_id)
                sub_request = TaskRequest(
                    sender_id=self.agent_id,
                    receiver_id=agent_id,
                    task_description=request.task_description,
                    correlation_id=request.correlation_id,
                    parent_message_id=request.id,
                )
                parallel_tasks.append(agent.handle_task(sub_request))
            except Exception:
                continue

        parallel_results: list[TaskResult] = []
        if parallel_tasks:
            raw = await asyncio.gather(*parallel_tasks, return_exceptions=True)
            parallel_results = [r for r in raw if isinstance(r, TaskResult)]

        # Phase 2: Sequential risk analysis with all inputs
        combined = "\n\n".join(
            f"## {r.sender_id}\n{r.result_data}" for r in parallel_results
        )
        risk_request = TaskRequest(
            sender_id=self.agent_id,
            receiver_id=self.RISK_AGENT_ID,
            task_description=(
                f"다음 분석 결과를 기반으로 리스크를 평가하세요:\n\n{combined}"
            ),
            correlation_id=request.correlation_id,
            parent_message_id=request.id,
        )

        try:
            risk_agent = self.context.registry.get_agent(self.RISK_AGENT_ID)
            risk_result = await risk_agent.handle_task(risk_request)
            all_results = parallel_results + [risk_result]
        except Exception:
            all_results = parallel_results

        # Phase 3: Synthesize everything
        return await self._synthesize_results(request, all_results)
