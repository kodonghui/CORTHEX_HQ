"""
CEO Orchestrator: routes CEO commands to the correct division.

Flow:
1. CEO types a command in CLI
2. Orchestrator classifies the command (which division?)
3. Creates a TaskRequest and sends to the correct agent
4. Collects TaskResult
5. Optionally notifies the secretary
6. Returns result to CLI
"""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from src.core.message import TaskRequest, TaskResult

if TYPE_CHECKING:
    from src.core.registry import AgentRegistry
    from src.llm.router import ModelRouter

logger = logging.getLogger("corthex.orchestrator")


class Orchestrator:
    """Routes CEO commands to the appropriate division head."""

    def __init__(self, registry: AgentRegistry, model_router: ModelRouter) -> None:
        self.registry = registry
        self.model_router = model_router

    async def process_command(self, user_input: str) -> TaskResult:
        """Main entry: classify and route a CEO command."""
        # Step 1: Classify the command
        classification = await self._classify_command(user_input)
        target_id = classification.get("target_agent_id", "")

        logger.info(
            "명령 분류: target=%s, reason=%s",
            target_id,
            classification.get("reason", ""),
        )

        # Step 2: Build TaskRequest
        request = TaskRequest(
            sender_id="ceo",
            receiver_id=target_id,
            task_description=user_input,
            context={"classification": classification},
        )

        # Step 3: Dispatch to target agent
        try:
            agent = self.registry.get_agent(target_id)
            result = await agent.handle_task(request)
        except Exception as e:
            logger.error("명령 처리 실패: %s", e)
            result = TaskResult(
                sender_id="orchestrator",
                receiver_id="ceo",
                correlation_id=request.correlation_id,
                success=False,
                result_data={"error": str(e)},
                summary=f"오류: {e}",
            )

        return result

    async def _classify_command(self, user_input: str) -> dict:
        """Use LLM to determine which division handles this command."""
        heads = self.registry.list_division_heads()
        heads_text = "\n".join(
            f"- agent_id: \"{h['agent_id']}\" | {h['name_ko']} | 담당: {', '.join(h['capabilities'])}"
            for h in heads
        )

        prompt = (
            "당신은 CORTHEX HQ의 명령 라우터입니다.\n\n"
            f"## 사용 가능한 사업부\n{heads_text}\n\n"
            "추가로 'chief_of_staff' (비서실장)에게 보낼 수도 있습니다.\n"
            "비서실장 담당: 보고서 요약, 일정 추적, 사업부 간 중계, 일반 질문\n\n"
            f"## CEO 명령\n{user_input}\n\n"
            "위 명령을 처리할 가장 적합한 에이전트를 선택하세요.\n"
            '반드시 JSON 형식으로만 응답: {"target_agent_id": "...", "reason": "..."}'
        )

        response = await self.model_router.complete(
            model_name="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )

        return self._parse_json(response.content)

    def _parse_json(self, text: str) -> dict:
        """Extract JSON object from LLM response."""
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        # Fallback to chief_of_staff
        return {"target_agent_id": "chief_of_staff", "reason": "분류 실패, 비서실로 전달"}
