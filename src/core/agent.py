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
from src.core.quality_gate import QualityGate

if TYPE_CHECKING:
    from src.llm.router import ModelRouter
    from src.tools.pool import ToolPool
    from src.core.context import SharedContext
    from src.core.memory import MemoryManager

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
    reasoning_effort: str = ""  # "", "low", "medium", "high"
    cli_owner: str = ""  # ceo | sister — CLI 소유자 필터
    org: str = ""  # 조직 스코프
    dormant: bool = False  # 비활성 에이전트
    telegram_code: str = ""  # 텔레그램 코드


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
        self._memory_manager: Optional[MemoryManager] = None

    def set_memory_manager(self, mm: MemoryManager) -> None:
        """메모리 매니저를 주입합니다."""
        self._memory_manager = mm

    @property
    def agent_id(self) -> str:
        return self.config.agent_id

    async def handle_task(self, request: TaskRequest) -> TaskResult:
        """Main entry point. Handles a task request end-to-end with retry."""
        start = time.monotonic()
        self.context.log_message(request)
        logger.info("[%s] 작업 수신: %s", self.agent_id, request.task_description[:80])

        # context에서 batch 모드 플래그 설정
        self._use_batch = request.context.get("use_batch", False)

        max_retries = self.config.max_retries
        last_error: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    wait = 2 ** (attempt - 1)  # 지수 백오프: 1초, 2초
                    logger.info("[%s] 재시도 %d/%d (대기 %d초)", self.agent_id, attempt, max_retries, wait)
                    await asyncio.sleep(wait)

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
                    task_description=request.task_description,
                    execution_time_seconds=round(elapsed, 2),
                )

                self.context.log_message(result)
                logger.info("[%s] 작업 완료 (%.1f초)", self.agent_id, elapsed)

                # 산출물을 부서별/날짜별 아카이브에 저장
                self._save_to_archive(request.task_description, result)

                # 성공 시 메모리 자동 추출 (비동기, 실패해도 무시)
                if self._memory_manager:
                    asyncio.create_task(
                        self._extract_memory(request.task_description, summary)
                    )

                return result

            except Exception as e:
                last_error = e
                logger.error("[%s] 오류 발생 (시도 %d/%d): %s", self.agent_id, attempt + 1, max_retries + 1, e)
                if attempt < max_retries:
                    continue  # 재시도

        # 모든 재시도 실패
        elapsed = time.monotonic() - start
        result = TaskResult(
            sender_id=self.agent_id,
            receiver_id=request.sender_id,
            parent_message_id=request.id,
            correlation_id=request.correlation_id,
            success=False,
            result_data={"error": str(last_error)},
            summary=f"오류 ({max_retries + 1}회 시도 후 실패): {last_error}",
            task_description=request.task_description,
            execution_time_seconds=round(elapsed, 2),
        )

        self.context.log_message(result)
        logger.info("[%s] 작업 실패 (%.1f초, %d회 재시도)", self.agent_id, elapsed, max_retries)

        self._save_to_archive(request.task_description, result)
        return result

    async def _extract_memory(self, task_desc: str, summary: str) -> None:
        """작업 완료 후 핵심 학습 사항을 메모리에 자동 저장합니다."""
        try:
            response = await self.model_router.complete(
                model_name="gpt-5-mini",  # 저렴한 모델 사용
                messages=[
                    {"role": "system", "content": (
                        "당신은 AI 에이전트의 학습 사항을 추출하는 도우미입니다.\n"
                        "작업 내용과 결과를 보고, 향후 같은 종류의 작업에서 기억해둘 만한\n"
                        "핵심 교훈 1~3개를 추출하세요.\n"
                        "반드시 JSON 배열로만 응답하세요:\n"
                        '[{"key": "짧은 제목", "value": "학습 내용"}]'
                    )},
                    {"role": "user", "content": f"작업: {task_desc}\n결과 요약: {summary}"},
                ],
                temperature=0.0,
                agent_id=self.agent_id,
            )
            import json as _json
            import re as _re
            match = _re.search(r'\[.*\]', response.content, _re.DOTALL)
            if match:
                items = _json.loads(match.group())
                for item in items[:3]:
                    key = item.get("key", "")
                    value = item.get("value", "")
                    if key and value:
                        self._memory_manager.add(self.agent_id, key, value, source="auto")
        except Exception as e:
            logger.debug("[%s] 메모리 추출 실패 (무시): %s", self.agent_id, e)

    def _save_to_archive(self, task_description: str, result: TaskResult) -> None:
        """산출물을 부서별/날짜별 아카이브에 저장."""
        try:
            from src.core.report_saver import save_agent_report
            save_agent_report(self.config, task_description, result)
        except Exception as e:
            logger.warning("[%s] 아카이브 저장 실패 (무시): %s", self.agent_id, e)

    @abstractmethod
    async def execute(self, request: TaskRequest) -> Any:
        """Subclass-specific logic."""
        ...

    async def think(self, messages: list[dict[str, str]]) -> str:
        """Call the LLM through the model router with memory injection."""
        # 메모리 주입: 시스템 프롬프트에 장기 기억 추가
        if self._memory_manager:
            mem_context = self._memory_manager.get_context_string(self.agent_id)
            if mem_context and messages and messages[0].get("role") == "system":
                messages = list(messages)  # 원본 보호
                messages[0] = {
                    "role": "system",
                    "content": messages[0]["content"] + mem_context,
                }

        # context에서 batch 모드 확인
        use_batch = getattr(self, '_use_batch', False)
        response = await self.model_router.complete(
            model_name=self.config.model_name,
            messages=messages,
            temperature=self.config.temperature,
            agent_id=self.agent_id,
            reasoning_effort=self.config.reasoning_effort or None,
            use_batch=use_batch,
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
    Quality gate: reviews subordinate results and rejects low quality.
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

        # Step 3: Quality gate - review and retry if needed
        results = await self._quality_review(results, plan, request)

        # Step 4: Synthesize results
        return await self._synthesize_results(request, results, errors)

    async def _quality_review(
        self,
        results: list[TaskResult],
        plan: list[dict[str, str]],
        parent_request: TaskRequest,
    ) -> list[TaskResult]:
        """품질 게이트: 부하 결과를 검수하고 미달 시 반려/재시도."""
        quality_gate = self.context.quality_gate
        if not quality_gate:
            return results

        reviewed: list[TaskResult] = []
        retry_tasks: list[tuple[TaskResult, dict[str, str], str]] = []

        # Step 1: Review each result
        for result in results:
            task_desc = ""
            for item in plan:
                if item.get("assignee_id") == result.sender_id:
                    task_desc = item.get("task", "")
                    break

            # Rule-based check first (free)
            rule_review = quality_gate.rule_based_check(result.result_data, task_desc)

            if rule_review.passed:
                # Passed rule check -> LLM review
                llm_review = await quality_gate.llm_review(
                    result.result_data,
                    task_desc,
                    self.model_router,
                    reviewer_id=self.agent_id,
                    division=self.config.division,
                )
                quality_gate.record_review(
                    llm_review, self.agent_id, result.sender_id, task_desc,
                )
                if llm_review.passed:
                    reviewed.append(result)
                else:
                    logger.info(
                        "[%s] 품질 반려: %s (점수: %d, 사유: %s)",
                        self.agent_id, result.sender_id,
                        llm_review.score, llm_review.rejection_reason,
                    )
                    plan_item = {"assignee_id": result.sender_id, "task": task_desc}
                    retry_tasks.append((result, plan_item, llm_review.rejection_reason))
            else:
                quality_gate.record_review(
                    rule_review, self.agent_id, result.sender_id, task_desc,
                )
                logger.info(
                    "[%s] 규칙 반려: %s (사유: %s)",
                    self.agent_id, result.sender_id, rule_review.rejection_reason,
                )
                plan_item = {"assignee_id": result.sender_id, "task": task_desc}
                retry_tasks.append((result, plan_item, rule_review.rejection_reason))

        # Step 2: Retry rejected tasks (max 1 retry each)
        if retry_tasks:
            retry_results = await self._retry_rejected(retry_tasks, parent_request)
            for retry_result in retry_results:
                # Re-review the retry
                task_desc = ""
                for _, plan_item, _ in retry_tasks:
                    if plan_item["assignee_id"] == retry_result.sender_id:
                        task_desc = plan_item["task"]
                        break
                re_review = quality_gate.rule_based_check(retry_result.result_data, task_desc)
                quality_gate.record_review(
                    re_review, self.agent_id, retry_result.sender_id, task_desc,
                    is_retry=True,
                )
                # Accept retry result regardless (already retried once)
                reviewed.append(retry_result)

        return reviewed

    async def _retry_rejected(
        self,
        retry_tasks: list[tuple[TaskResult, dict[str, str], str]],
        parent_request: TaskRequest,
    ) -> list[TaskResult]:
        """반려된 작업을 피드백과 함께 1회 재시도."""
        tasks = []
        for original_result, plan_item, rejection_reason in retry_tasks:
            assignee_id = plan_item["assignee_id"]
            original_task = plan_item["task"]

            try:
                agent = self.context.registry.get_agent(assignee_id)
            except Exception:
                continue

            # Retry with feedback about what was wrong
            retry_desc = (
                f"{original_task}\n\n"
                f"[품질 검수 반려] 이전 결과가 반려되었습니다.\n"
                f"반려 사유: {rejection_reason}\n"
                f"위 사유를 보완하여 더 구체적이고 정확하게 다시 작성해주세요."
            )

            sub_request = TaskRequest(
                sender_id=self.agent_id,
                receiver_id=assignee_id,
                task_description=retry_desc,
                correlation_id=parent_request.correlation_id,
                parent_message_id=parent_request.id,
                context=parent_request.context,
            )
            tasks.append(agent.handle_task(sub_request))

        if not tasks:
            return []

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        results = []
        for r in raw_results:
            if isinstance(r, TaskResult):
                results.append(r)
            elif isinstance(r, Exception):
                logger.error("[%s] 재시도 작업 실패: %s", self.agent_id, r)
        return results

    async def _plan_decomposition(self, request: TaskRequest) -> list[dict[str, str]]:
        """Ask LLM to break the task into sub-tasks for subordinates."""
        if not self.config.subordinate_ids:
            return []

        subordinate_info = self._describe_subordinates()

        # Build context section (includes conversation history if available)
        context_section = ""
        conv_history = request.context.get("conversation_history", "")
        if conv_history:
            context_section = f"## 이전 대화 맥락\n{conv_history}\n\n"

        messages = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": (
                f"{context_section}"
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
    ) -> tuple[list[TaskResult], list[str]]:
        """Send sub-tasks to subordinates in parallel."""
        tasks = []
        dispatched_ids: list[str] = []
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
            dispatched_ids.append(assignee_id)

        if not tasks:
            return [], []

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        results = []
        errors = []
        for i, r in enumerate(raw_results):
            if isinstance(r, TaskResult):
                results.append(r)
            elif isinstance(r, Exception):
                aid = dispatched_ids[i]
                logger.error("[%s] 부하 작업 실패 (%s): %s", self.agent_id, aid, r)
                errors.append(f"{aid}: {r}")
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

        # 결과가 1개면 재합성 없이 그대로 반환 (중복 방지 + 토큰 절약)
        if len(results) == 1:
            return results[0].result_data

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
    Supports multi-step 'deep work' for complex tasks.
    """

    async def execute(self, request: TaskRequest) -> Any:
        max_steps = request.context.get("max_steps", 1)

        if max_steps <= 1:
            # Original single-shot behavior
            messages = [
                {"role": "system", "content": self.config.system_prompt},
                {"role": "user", "content": request.task_description},
            ]
            return await self.think(messages)

        # Deep work mode: multi-step autonomous loop
        return await self._deep_work(request, max_steps)

    async def _deep_work(self, request: TaskRequest, max_steps: int) -> str:
        """Multi-step reasoning loop for complex tasks."""
        from src.core.message import StatusUpdate

        accumulated: list[str] = []

        # Step 1: Plan
        plan_messages = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": (
                f"## 업무\n{request.task_description}\n\n"
                f"이 업무를 {max_steps - 1}단계로 나누어 실행할 계획을 세우세요.\n"
                "JSON 배열로만 응답하세요: [\"단계1 설명\", \"단계2 설명\", ...]\n"
                "마지막 단계는 항상 '최종 결과물 작성'이어야 합니다."
            )},
        ]
        plan_raw = await self.think(plan_messages)
        steps = self._parse_steps(plan_raw, max_steps - 1)

        # Broadcast: planning complete
        self.context.log_message(StatusUpdate(
            sender_id=self.agent_id,
            receiver_id=request.sender_id,
            correlation_id=request.correlation_id,
            progress_pct=0.0,
            current_step=f"0/{len(steps)}",
            detail="작업 계획 수립 완료",
        ))

        # Steps 2..N: Execute each step
        for i, step_desc in enumerate(steps):
            context_summary = "\n---\n".join(accumulated[-3:])

            step_messages = [
                {"role": "system", "content": self.config.system_prompt},
                {"role": "user", "content": (
                    f"## 원래 업무\n{request.task_description}\n\n"
                    + (f"## 지금까지의 작업 결과\n{context_summary}\n\n" if context_summary else "")
                    + f"## 현재 단계 ({i+1}/{len(steps)})\n{step_desc}\n\n"
                    "위 단계를 실행하고 결과를 상세히 작성하세요."
                )},
            ]
            step_result = await self.think(step_messages)
            accumulated.append(f"### 단계 {i+1}: {step_desc}\n{step_result}")

            # Broadcast progress
            self.context.log_message(StatusUpdate(
                sender_id=self.agent_id,
                receiver_id=request.sender_id,
                correlation_id=request.correlation_id,
                progress_pct=(i + 1) / len(steps),
                current_step=f"{i+1}/{len(steps)}",
                detail=step_desc,
            ))

        return "\n\n".join(accumulated)

    @staticmethod
    def _parse_steps(plan_raw: str, target_count: int) -> list[str]:
        """Parse step list from LLM output."""
        match = re.search(r'\[.*\]', plan_raw, re.DOTALL)
        if match:
            try:
                steps = json.loads(match.group())
                if isinstance(steps, list) and all(isinstance(s, str) for s in steps):
                    return steps[:target_count]
            except json.JSONDecodeError:
                pass
        return [f"단계 {i+1} 실행" for i in range(target_count)]


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
