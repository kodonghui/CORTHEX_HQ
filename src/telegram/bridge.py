"""
CORTHEX <-> Telegram 양방향 브릿지.

- 텔레그램 명령 → Orchestrator 실행 → 결과를 텔레그램 + 웹 대시보드에 전달
- 에이전트 이벤트 → 텔레그램에 실시간 상태 전송
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from src.telegram import formatter

if TYPE_CHECKING:
    from telegram import Bot

    from src.core.message import Message, MessageType
    from src.core.orchestrator import Orchestrator
    from src.core.registry import AgentRegistry
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
    ) -> None:
        self.bot = bot
        self.orchestrator = orchestrator
        self.ws_manager = ws_manager
        self.model_router = model_router
        self.registry = registry
        self.ceo_chat_id = ceo_chat_id
        self._processing = False
        self._lock = asyncio.Lock()

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

            # 4. CORTHEX 처리 (기존 로직 그대로)
            result = await self.orchestrator.process_command(text)

            # 5. 결과를 텔레그램으로 전송
            messages = formatter.format_result(result)
            for msg_text in messages:
                await self.bot.send_message(
                    chat_id=self.ceo_chat_id,
                    text=msg_text,
                    parse_mode="Markdown",
                )

            # 6. 웹 대시보드에 결과 전달
            await self.ws_manager.broadcast("result", {
                "success": result.success,
                "content": str(result.result_data or result.summary),
                "sender_id": result.sender_id,
                "time_seconds": result.execution_time_seconds,
                "cost": self.model_router.cost_tracker.total_cost if self.model_router else 0,
                "source": "telegram",
            })

            # 7. 상태 메시지 삭제 (깔끔하게)
            try:
                await status_msg.delete()
            except Exception:
                pass

            # 8. 에이전트 상태 idle로 복원
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

    async def on_agent_event(self, msg: Message) -> None:
        """에이전트 이벤트를 텔레그램에 전달 (작업 시작/완료만)."""
        from src.core.message import MessageType

        if not self._processing:
            return

        try:
            if msg.type == MessageType.TASK_REQUEST:
                text = formatter.format_agent_status(msg.receiver_id, "working")
                await self.bot.send_message(
                    chat_id=self.ceo_chat_id, text=text, parse_mode="Markdown",
                )
            elif msg.type == MessageType.TASK_RESULT:
                text = formatter.format_agent_status(msg.sender_id, "done")
                await self.bot.send_message(
                    chat_id=self.ceo_chat_id, text=text, parse_mode="Markdown",
                )
        except Exception as e:
            logger.debug("텔레그램 상태 전송 실패 (무시): %s", e)
