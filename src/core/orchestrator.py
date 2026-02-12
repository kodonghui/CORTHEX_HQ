"""
CEO Orchestrator: routes all CEO commands through the Chief of Staff.

Flow:
1. CEO types a command in CLI
2. Orchestrator sends it to the Chief of Staff (비서실장)
3. Chief of Staff decomposes and delegates to managers
4. Collects TaskResult
5. Saves report to reports/ directory
6. Auto-pushes to GitHub
7. Returns result to CLI
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.core.message import TaskRequest, TaskResult
from src.core.report_saver import save_report
from src.core.git_sync import auto_push

if TYPE_CHECKING:
    from src.core.registry import AgentRegistry
    from src.llm.router import ModelRouter

logger = logging.getLogger("corthex.orchestrator")


class Orchestrator:
    """Routes all CEO commands through the Chief of Staff (비서실장)."""

    def __init__(self, registry: AgentRegistry, model_router: ModelRouter) -> None:
        self.registry = registry
        self.model_router = model_router

    async def process_command(self, user_input: str) -> TaskResult:
        """Main entry: all commands go through chief_of_staff."""
        request = TaskRequest(
            sender_id="ceo",
            receiver_id="chief_of_staff",
            task_description=user_input,
            context={},
        )

        logger.info("CEO 명령 → 비서실장: %s", user_input[:80])

        try:
            agent = self.registry.get_agent("chief_of_staff")
            result = await agent.handle_task(request)
        except Exception as e:
            logger.error("명령 처리 실패: %s", e)
            result = TaskResult(
                sender_id="chief_of_staff",
                receiver_id="ceo",
                correlation_id=request.correlation_id,
                success=False,
                result_data={"error": str(e)},
                summary=f"오류: {e}",
            )

        # 보고서 저장 → GitHub 자동 업로드
        await self._save_and_upload(user_input, result)

        return result

    async def _save_and_upload(self, command: str, result: TaskResult) -> None:
        """보고서를 파일로 저장하고 GitHub에 자동 푸시."""
        filepath = save_report(command, result)
        if filepath:
            await auto_push(filepath, command)
