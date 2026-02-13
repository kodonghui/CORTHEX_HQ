"""
CORTHEX <-> Telegram 양방향 브릿지.

- 텔레그램 명령 → Orchestrator 실행 → 결과를 텔레그램 + 웹 대시보드에 전달
- 에이전트 이벤트 → 텔레그램에 실시간 상태 전송
- 결과를 부서별로 정리하여 보고
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from src.telegram import formatter

if TYPE_CHECKING:
    from telegram import Bot

    from src.core.context import SharedContext
    from src.core.message import Message, MessageType
    from src.core.orchestrator import Orchestrator
    from src.core.registry import AgentRegistry
    from src.core.task_store import TaskStore
    from src.llm.router import ModelRouter
    from web.ws_manager import ConnectionManager

logger = logging.getLogger("corthex.telegram.bridge")


class TelegramBridge:
    """CORTHEX <-> Telegram 양방향 브릿지."""

    def __init__(
        self,
        bot: Bot,
        orchestrator: Orchestrator,
        ws_manager: ConnectionManager,
        model_router: ModelRouter,
        registry: AgentRegistry,
        ceo_chat_id: int,
        context: SharedContext | None = None,
        task_store: TaskStore | None = None,
    ) -> None:
        self.bot = bot
        self.orchestrator = orchestrator
        self.ws_manager = ws_manager
        self.model_router = model_router
        self.registry = registry
        self.ceo_chat_id = ceo_chat_id
        self.context = context
        self.task_store = task_store
        self._processing = False
        self._lock = asyncio.Lock()
        # 마지막 명령 텍스트 (부서별 보고서 헤더에 사용)
        self._last_command: str = ""
        # 마지막 전체 보고서 캐시 (/detail 명령에 사용)
        self._last_full_report: str | None = None
        # 에이전트별 진행 상황 메시지 ID (메시지 수정용)
        self._status_messages: dict[str, int] = {}

    async def handle_command(self, text: str) -> None:
        """텔레그램 CEO 명령을 CORTHEX로 전달하고 결과를 양쪽에 전송."""
        async with self._lock:
            if self._processing:
                await self.bot.send_message(
                    chat_id=self.ceo_chat_id,
                    text="\u23f3 이전 명령을 처리 중입니다. 완료 후 다시 보내주세요.",
                )
                return

            self._processing = True

        self._last_command = text
        self._status_messages.clear()

        try:
            # 1. 처리 시작 알림 (텔레그램)
            status_msg = await self.bot.send_message(
                chat_id=self.ceo_chat_id,
                text=formatter.format_processing(text),
                parse_mode="Markdown",
            )

            # 2. 웹 대시보드에 텔레그램 명령 알림
            await self.ws_manager.broadcast("telegram_command", {
                "text": text,
                "source": "telegram",
            })

            # 3. 에이전트 상태 초기화
            if self.registry:
                for agent in self.registry.list_all():
                    await self.ws_manager.send_agent_status(
                        agent.config.agent_id, "idle"
                    )

            # 4. CORTHEX 처리
            result = await self.orchestrator.process_command(text)

            # 5. 전체 보고서 캐시 (/detail 명령용)
            self._last_full_report = str(result.result_data or result.summary)

            # 6. 결과를 부서별로 정리하여 텔레그램으로 전송
            dept_data = self._organize_by_department(result.correlation_id)

            if dept_data:
                messages = formatter.format_department_report(
                    result, dept_data, command=text,
                )
            else:
                # 부서 데이터가 없으면 기존 방식 사용
                messages = formatter.format_result(result)

            for msg_text in messages:
                await self.bot.send_message(
                    chat_id=self.ceo_chat_id,
                    text=msg_text,
                    parse_mode="Markdown",
                )
                await asyncio.sleep(0.3)  # 메시지 순서 보장

            # 7. 웹 대시보드에 결과 전달
            await self.ws_manager.broadcast("result", {
                "success": result.success,
                "content": str(result.result_data or result.summary),
                "sender_id": result.sender_id,
                "time_seconds": result.execution_time_seconds,
                "cost": self.model_router.cost_tracker.total_cost if self.model_router else 0,
                "source": "telegram",
            })

            # 8. 상태 메시지 삭제 (깔끔하게)
            try:
                await status_msg.delete()
            except Exception:
                pass

            # 9. 에이전트 상태 idle로 복원
            if self.registry:
                for agent in self.registry.list_all():
                    await self.ws_manager.send_agent_status(
                        agent.config.agent_id, "idle"
                    )

        except Exception as e:
            logger.error("텔레그램 명령 처리 실패: %s", e)
            await self.bot.send_message(
                chat_id=self.ceo_chat_id,
                text=f"\u274c 오류 발생: {e}",
            )
        finally:
            self._processing = False
            self._status_messages.clear()

    async def on_agent_event(self, msg: Message) -> None:
        """에이전트 이벤트를 텔레그램에 실시간 전달.

        - TASK_REQUEST: 작업 시작 알림 (새 메시지)
        - STATUS_UPDATE: 진행 상황 업데이트 (기존 메시지 수정)
        - TASK_RESULT: 작업 완료 알림 (기존 메시지 수정)
        """
        from src.core.message import MessageType

        if not self._processing:
            return

        try:
            if msg.type == MessageType.TASK_REQUEST:
                # 새 에이전트에게 작업 배정 → 새 메시지 전송
                agent_id = msg.receiver_id
                name_ko, division = self._get_agent_info(agent_id)
                text = formatter.format_agent_working(agent_id, name_ko, division)
                sent = await self.bot.send_message(
                    chat_id=self.ceo_chat_id, text=text, parse_mode="Markdown",
                )
                self._status_messages[agent_id] = sent.message_id

            elif msg.type == MessageType.STATUS_UPDATE:
                # 진행 상황 → 기존 메시지 수정 (메시지 폭탄 방지)
                agent_id = msg.sender_id
                name_ko, division = self._get_agent_info(agent_id)
                text = formatter.format_progress_update(
                    name_ko=name_ko,
                    division=division,
                    progress_pct=msg.progress_pct,
                    current_step=msg.current_step,
                    detail=msg.detail,
                )
                prev_msg_id = self._status_messages.get(agent_id)
                if prev_msg_id:
                    try:
                        await self.bot.edit_message_text(
                            chat_id=self.ceo_chat_id,
                            message_id=prev_msg_id,
                            text=text,
                            parse_mode="Markdown",
                        )
                    except Exception:
                        # 메시지 수정 실패 시 새 메시지 전송
                        sent = await self.bot.send_message(
                            chat_id=self.ceo_chat_id, text=text, parse_mode="Markdown",
                        )
                        self._status_messages[agent_id] = sent.message_id
                else:
                    sent = await self.bot.send_message(
                        chat_id=self.ceo_chat_id, text=text, parse_mode="Markdown",
                    )
                    self._status_messages[agent_id] = sent.message_id

            elif msg.type == MessageType.TASK_RESULT:
                # 작업 완료 → 기존 메시지를 완료 상태로 수정
                agent_id = msg.sender_id
                name_ko, division = self._get_agent_info(agent_id)
                text = formatter.format_agent_done(
                    name_ko, division, msg.execution_time_seconds,
                )
                prev_msg_id = self._status_messages.get(agent_id)
                if prev_msg_id:
                    try:
                        await self.bot.edit_message_text(
                            chat_id=self.ceo_chat_id,
                            message_id=prev_msg_id,
                            text=text,
                            parse_mode="Markdown",
                        )
                    except Exception:
                        await self.bot.send_message(
                            chat_id=self.ceo_chat_id, text=text, parse_mode="Markdown",
                        )
                else:
                    await self.bot.send_message(
                        chat_id=self.ceo_chat_id, text=text, parse_mode="Markdown",
                    )

        except Exception as e:
            logger.debug("텔레그램 상태 전송 실패 (무시): %s", e)

    # ─── 부서별 정리 ───

    def _organize_by_department(self, correlation_id: str) -> dict[str, list[dict]]:
        """correlation_id로 중간 보고서를 부서별로 정리.

        SharedContext._conversations에서 해당 명령의 모든 TaskResult 메시지를 가져와서
        에이전트의 소속 부서별로 그룹화합니다.
        """
        if not self.context:
            return {}

        from src.core.message import MessageType

        messages = self.context.get_conversation(correlation_id)
        by_department: dict[str, list[dict]] = {}

        for msg in messages:
            if msg.type != MessageType.TASK_RESULT:
                continue
            # 비서실장 최종 결과는 제외 (이미 요약에 포함)
            if msg.sender_id == "chief_of_staff":
                continue

            name_ko, division = self._get_agent_info(msg.sender_id)
            top_division = division.split(".")[0] if division else "unknown"

            by_department.setdefault(top_division, []).append({
                "agent_id": msg.sender_id,
                "name_ko": name_ko,
                "division": division,
                "summary": msg.summary,
                "result_data": str(msg.result_data)[:500] if msg.result_data else "",
                "execution_time": msg.execution_time_seconds,
                "success": msg.success,
            })

        return by_department

    def _get_agent_info(self, agent_id: str) -> tuple[str, str]:
        """에이전트 ID로 한국어 이름과 부서를 가져옴."""
        if not self.registry:
            return agent_id, "unknown"
        try:
            agent = self.registry.get_agent(agent_id)
            return agent.config.name_ko, agent.config.division or "unknown"
        except Exception:
            return agent_id, "unknown"
