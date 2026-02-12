"""
Agent base classes for CORTHEX HQ.

Hierarchy:
  BaseAgent (abstract)
  ├── ManagerAgent   - decomposes tasks, delegates to subordinates
  ├── SpecialistAgent - focused domain work, no delegation
  └── WorkerAgent    - simple repeatable tasks
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Optional, TYPE_CHECKING

from pydantic import BaseModel, Field, ConfigDict

from src.core.message import TaskRequest, TaskResult, MessageType

if TYPE_CHECKING:
    from src.llm.router import ModelRouter
    from src.tools.pool import ToolPool
    from src.core.context import SharedContext

logger = logging.getLogger("corthex.agent")


class AgentConfig(BaseModel):
    """Configuration for an agent, loaded from agents.yaml."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    name: str
    name_ko: str
    role: str  # "division_head", "manager", "specialist", "worker"
    division: str
    model_name: str
    system_prompt: str
    capabilities: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    subordinate_ids: list[str] = Field(default_factory=list)
    superior_id: Optional[str] = None
    max_retries: int = 2
    temperature: float = 0.3


class BaseAgent(ABC):
    """
    Abstract base for all agents in CORTHEX HQ.

    Every agent can:
    - Receive a TaskRequest
    - Think (call LLM)
    - Optionally delegate to subordinates
    - Optionally invoke tools
    - Return a TaskResult
    """

    def __init__(
        self,
        config: AgentConfig,
        model_router: ModelRouter,
        tool_pool: ToolPool,
        context: SharedContext,
    ) -> None:
        self.config = config
        self.model_router = model_router
        self.tool_pool = tool_pool
        self.context = context

    @property
    def agent_id(self) -> str:
        return self.config.agent_id

    async def handle_task(self, request: TaskRequest) -> TaskResult:
        """Main entry point. Handles a task request end-to-end."""
        start = time.monotonic()
        self.context.log_message(request)
        logger.info("[%s] 작업 수신: %s", self.agent_id, request.task_description[:80])

        try:
            result_data = await self.execute(request)
            elapsed = time.monotonic() - start

            summary = await self._summarize(result_data)
            result = TaskResult(
                sender_id=self.agent_id,
                receiver_id=request.sender_id,
                parent_message_id=request.id,
                correlation_id=request.correlation_id,
                success=True,
                result_data=result_data,
                summary=summary,
                execution_time_seconds=round(elapsed, 2),
            )
        except Exception as e:
            elapsed = time.monotonic() - start
            logger.error("[%s] 오류 발생: %s", self.agent_id, e)
            result = TaskResult(
                sender_id=self.agent_id,
                receiver_id=request.sender_id,
                parent_message_id=request.id,
                correlation_id=request.correlation_id,
                success=False,
                result_data={"error": str(e)},
                summary=f"오류: {e}",
                execution_time_seconds=round(elapsed, 2),
            )

        self.context.log_message(result)
        logger.info("[%s] 작업 완료 (%.1f초)", self.agent_id, elapsed)
        return result

    @abstractmethod
    async def execute(self, request: TaskRequest) -> Any:
        """Subclass-specific logic."""
        ...

    async def think(self, messages: list[dict[str, str]]) -> str:
        """Call the LLM through the model router."""
        response = await self.model_router.complete(
            model_name=self.config.model_name,
            messages=messages,
            temperature=self.config.temperature,
            agent_id=self.agent_id,
        )
        return response.content

    async def use_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Invoke a tool from the shared pool."""
        from src.core.errors import ToolPermissionError

        if tool_name not in self.config.allowed_tools:
            raise ToolPermissionError(self.agent_id, tool_name)
        return await self.tool_pool.invoke(tool_name, caller_id=self.agent_id, **kwargs)

    async def _summarize(self, result: Any) -> str:
        """Generate a short summary for reporting upward."""
        text = str(result)
        if len(text) < 200:
            return text
        response = await self.model_router.complete(
            model_name=self.config.model_name,
            messages=[
                {"role": "system", "content": "주어진 내용을 한국어 1-2문장으로 요약하세요."},
                {"role": "user", "content": text[:3000]},
            ],
            temperature=0.0,
            agent_id=self.agent_id,
        )
        return response.content


class ManagerAgent(BaseAgent):
    """
    A manager decomposes tasks and delegates to subordinates.
    All subordinate tasks run in parallel via asyncio.gather.
    """

    async def execute(self, request: TaskRequest) -> Any:
        # Step 1: Plan decomposition
        plan = await self._plan_decomposition(request)

        if not plan:
            # No subordinates needed; handle directly
            return await self.think([
                {"role": "system", "content": self.config.system_prompt},
                {"role": "user", "content": request.task_description},
            ])

        # Step 2: Delegate sub-tasks in parallel
        results, errors = await self._delegate_subtasks(plan, request)

        # Step 3: Synthesize results
        return await self._synthesize_results(request, results, errors)

    async def _plan_decomposition(self, request: TaskRequest) -> list[dict[str, str]]:
        """Ask LLM to break the task into sub-tasks for subordinates."""
        if not self.config.subordinate_ids:
            return []

        subordinate_info = self._describe_subordinates()
        messages = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": (
                f"## 업무 지시\n{request.task_description}\n\n"
                f"## 사용 가능한 부하 에이전트\n{subordinate_info}\n\n"
                "위 업무를 부하 에이전트들에게 배분하세요.\n"
                "반드시 아래 JSON 배열 형식으로만 응답하세요:\n"
                '[{"assignee_id": "에이전트ID", "task": "세부 업무 내용"}]\n'
                "해당 없는 에이전트는 제외하세요."
            )},
        ]
        response = await self.think(messages)
        return self._parse_plan_json(response)

    async def _delegate_subtasks(
        self, plan: list[dict[str, str]], parent_request: TaskRequest
    ) -> list[TaskResult]:
        """Send sub-tasks to subordinates in parallel."""
        tasks = []
        for item in plan:
            assignee_id = item.get("assignee_id", "")
            task_desc = item.get("task", "")
            if not assignee_id or not task_desc:
                continue

            try:
                agent = self.context.registry.get_agent(assignee_id)
            except Exception:
                logger.warning("[%s] 부하 에이전트를 찾을 수 없음: %s", self.agent_id, assignee_id)
                continue

            sub_request = TaskRequest(
                sender_id=self.agent_id,
                receiver_id=assignee_id,
                task_description=task_desc,
                correlation_id=parent_request.correlation_id,
                parent_message_id=parent_request.id,
                context=parent_request.context,
            )
            tasks.append(agent.handle_task(sub_request))

        if not tasks:
            return []

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        results = []
        errors = []
        for i, r in enumerate(raw_results):
            if isinstance(r, TaskResult):
                results.append(r)
            elif isinstance(r, Exception):
                assignee_id = plan[i].get("assignee_id", "unknown") if i < len(plan) else "unknown"
                logger.error("[%s] 부하 작업 실패 (%s): %s", self.agent_id, assignee_id, r)
                errors.append(f"{assignee_id}: {r}")
        return results, errors

    async def _synthesize_results(
        self, request: TaskRequest, results: list[TaskResult], errors: list[str] | None = None,
    ) -> str:
        """Combine subordinate results into a unified response."""
        if not results:
            error_detail = "\n".join(f"- {e}" for e in (errors or []))
            return (
                "부하 에이전트로부터 결과를 받지 못했습니다.\n\n"
                f"실패 원인:\n{error_detail}" if error_detail
                else "부하 에이전트로부터 결과를 받지 못했습니다."
            )

        result_text = "\n\n".join(
            f"### [{r.sender_id}]\n{r.result_data}" for r in results
        )
        messages = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": (
                f"## 원래 업무\n{request.task_description}\n\n"
                f"## 부하 에이전트 결과\n{result_text}\n\n"
                "위 결과를 종합하여 하나의 체계적인 보고서로 작성하세요."
            )},
        ]
        return await self.think(messages)

    def _describe_subordinates(self) -> str:
        """Get info about subordinates for the LLM prompt."""
        lines = []
        for sid in self.config.subordinate_ids:
            try:
                agent = self.context.registry.get_agent(sid)
                caps = ", ".join(agent.config.capabilities) or "일반"
                lines.append(f"- agent_id: \"{sid}\" | 이름: {agent.config.name_ko} | 능력: {caps}")
            except Exception:
                lines.append(f"- agent_id: \"{sid}\" | (정보 없음)")
        return "\n".join(lines) if lines else "(부하 에이전트 없음)"

    def _parse_plan_json(self, response: str) -> list[dict[str, str]]:
        """Extract JSON array from LLM response."""
        # Try to find JSON array in the response
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning(
                    "[%s] JSON 파싱 실패, 첫 번째 부하에게 전체 작업 할당. 응답: %s",
                    self.agent_id,
                    response[:200],
                )
        else:
            logger.warning(
                "[%s] LLM 응답에서 JSON 배열을 찾을 수 없음. 응답: %s",
                self.agent_id,
                response[:200],
            )
        # Fallback: assign entire task to first subordinate
        if self.config.subordinate_ids:
            return [{"assignee_id": self.config.subordinate_ids[0], "task": response}]
        return []


class SpecialistAgent(BaseAgent):
    """
    A specialist does focused work using domain expertise.
    Does NOT delegate to subordinates.
    """

    async def execute(self, request: TaskRequest) -> Any:
        messages = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": request.task_description},
        ]
        return await self.think(messages)


class WorkerAgent(BaseAgent):
    """
    A worker performs simple, repeatable tasks.
    Always uses the cheapest model.
    """

    async def execute(self, request: TaskRequest) -> Any:
        messages = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": request.task_description},
        ]
        return await self.think(messages)
