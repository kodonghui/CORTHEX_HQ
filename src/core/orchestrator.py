"""
CEO Orchestrator: routes all CEO commands through the Chief of Staff.

Flow:
1. CEO types a command in CLI
2. Orchestrator sends it to the Chief of Staff (비서실장)
3. 비서실장 → 팀장(Manager) → Specialist/Worker → 팀장 → 비서실장
4. 비서실장이 최종 TaskResult를 CEO에게 반환
5. reports/ 디렉토리에 보고서 저장
6. GitHub 자동 푸시

Supports conversation context: recent command-result pairs are passed
as context so follow-up questions can reference prior results.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.core.message import TaskRequest, TaskResult
from src.core.git_sync import auto_push_reports

if TYPE_CHECKING:
    from src.core.registry import AgentRegistry
    from src.llm.router import ModelRouter

logger = logging.getLogger("corthex.orchestrator")

_MAX_CONTEXT_TURNS = 5


@dataclass
class ConversationTurn:
    command: str
    summary: str


class Orchestrator:
    """Routes all CEO commands through the Chief of Staff (비서실장)."""

    def __init__(self, registry: AgentRegistry, model_router: ModelRouter) -> None:
        self.registry = registry
        self.model_router = model_router
        self._history: list[ConversationTurn] = []

    async def process_command(
        self, user_input: str, context: dict | None = None,
    ) -> TaskResult:
        """Main entry: all commands go through chief_of_staff."""
        # Build conversation context from recent history
        context_data = {}
        if self._history:
            history_lines = []
            for turn in self._history[-_MAX_CONTEXT_TURNS:]:
                history_lines.append(f"[CEO 명령] {turn.command}")
                history_lines.append(f"[결과 요약] {turn.summary}")
            context_data["conversation_history"] = "\n".join(history_lines)

        request = TaskRequest(
            sender_id="ceo",
            receiver_id="chief_of_staff",
            task_description=user_input,
            context={**(context or {}), **context_data},
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

        # Store in history for future context
        summary = result.summary or str(result.result_data)[:200]
        self._history.append(ConversationTurn(
            command=user_input,
            summary=summary,
        ))
        # Keep bounded
        if len(self._history) > _MAX_CONTEXT_TURNS * 2:
            self._history = self._history[-_MAX_CONTEXT_TURNS:]

        # 모든 에이전트 산출물이 저장된 후 한 번에 GitHub 푸시
        await auto_push_reports(user_input)

        return result

    @property
    def conversation_history(self) -> list[dict[str, str]]:
        """Return conversation history as a list of dicts for API."""
        return [
            {"command": t.command, "summary": t.summary}
            for t in self._history
        ]

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._history.clear()
