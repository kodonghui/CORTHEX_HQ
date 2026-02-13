"""
CORTHEX HQ - Telegram Bot.

CEO가 텔레그램에서 업무 지시를 내리고 보고서를 받을 수 있는 봇입니다.
FastAPI 서버의 asyncio 이벤트 루프 안에서 polling 방식으로 동작합니다.

명령어:
  /start  - 봇 시작 (chat_id 안내)
  /help   - 사용법
  /agents - 에이전트 목록
  /cost   - 비용 현황
  /health - 시스템 상태
  (일반 텍스트) - CEO 업무 지시
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from src.telegram.auth import TelegramAuth
from src.telegram.bridge import TelegramBridge
from src.telegram import formatter

if TYPE_CHECKING:
    from src.core.orchestrator import Orchestrator
    from src.core.registry import AgentRegistry
    from src.llm.router import ModelRouter
    from web.ws_manager import ConnectionManager

logger = logging.getLogger("corthex.telegram.bot")

# 모듈 레벨 참조 (핸들러에서 사용)
_auth: TelegramAuth | None = None
_bridge: TelegramBridge | None = None
_registry: AgentRegistry | None = None
_model_router: ModelRouter | None = None


# ─── Command Handlers ───


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start - 봇 시작."""
    if not update.effective_chat or not _auth:
        return

    chat_id = update.effective_chat.id

    if not _auth.is_configured:
        await update.message.reply_text(
            _auth.get_setup_message(chat_id),
            parse_mode="Markdown",
        )
        return

    if not _auth.is_authorized(chat_id):
        await update.message.reply_text("권한이 없습니다.")
        return

    await update.message.reply_text(
        "*CORTHEX HQ 텔레그램 봇*\n\n"
        "CEO 인증 완료.\n"
        "메시지를 보내면 업무 지시로 처리됩니다.\n\n"
        "/help 로 사용법을 확인하세요.",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help - 사용법."""
    if not _is_ceo(update):
        return

    await update.message.reply_text(
        "*CORTHEX HQ 사용법*\n\n"
        "*업무 지시*: 그냥 메시지를 보내면 됩니다\n"
        "  예: `삼성전자 투자 분석해줘`\n"
        "  예: `리트마스터 경쟁사 현황 정리해줘`\n\n"
        "*관리 명령어*:\n"
        "  /agents - 에이전트 목록\n"
        "  /cost   - 비용 현황\n"
        "  /health - 시스템 상태\n",
        parse_mode="Markdown",
    )


async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/agents - 에이전트 목록."""
    if not _is_ceo(update) or not _registry:
        return

    agents = []
    for agent in _registry.list_all():
        agents.append({
            "agent_id": agent.config.agent_id,
            "name_ko": agent.config.name_ko,
            "role": agent.config.role,
            "division": agent.config.division,
        })

    text = formatter.format_agent_list(agents)
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_cost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/cost - 비용 현황."""
    if not _is_ceo(update) or not _model_router:
        return

    tracker = _model_router.cost_tracker
    cost_data = {
        "total_cost": tracker.total_cost,
        "total_tokens": tracker.total_tokens,
        "total_calls": tracker.total_calls,
    }
    text = formatter.format_cost_summary(cost_data)
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/health - 시스템 상태."""
    if not _is_ceo(update) or not _registry or not _model_router:
        return

    from src.core.healthcheck import run_healthcheck
    report = await run_healthcheck(_registry, _model_router)
    text = formatter.format_health(report.to_dict())
    await update.message.reply_text(text, parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """일반 텍스트 = CEO 업무 지시."""
    if not _is_ceo(update) or not _bridge:
        return

    text = update.message.text.strip()
    if not text:
        return

    # 브릿지를 통해 CORTHEX에 전달 (비동기로 실행)
    asyncio.create_task(_bridge.handle_command(text))


# ─── Helpers ───


def _is_ceo(update: Update) -> bool:
    """CEO 인증 확인. 실패 시 응답 전송."""
    if not update.effective_chat or not update.message or not _auth:
        return False
    if not _auth.is_authorized(update.effective_chat.id):
        asyncio.create_task(
            update.message.reply_text("권한이 없습니다.")
        )
        return False
    return True


# ─── Bot Factory ───


async def create_bot(
    orchestrator: Orchestrator,
    ws_manager: ConnectionManager,
    model_router: ModelRouter,
    registry: AgentRegistry,
) -> Application:
    """텔레그램 봇 Application을 생성하고 반환합니다."""
    global _auth, _bridge, _registry, _model_router

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")

    _auth = TelegramAuth()
    _registry = registry
    _model_router = model_router

    # Application 생성
    application = Application.builder().token(token).build()

    # 브릿지 생성 (auth가 설정된 경우에만)
    if _auth.is_configured:
        _bridge = TelegramBridge(
            bot=application.bot,
            orchestrator=orchestrator,
            ws_manager=ws_manager,
            model_router=model_router,
            registry=registry,
            ceo_chat_id=int(os.getenv("TELEGRAM_CEO_CHAT_ID", "0")),
        )

    # 핸들러 등록
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("agents", cmd_agents))
    application.add_handler(CommandHandler("cost", cmd_cost))
    application.add_handler(CommandHandler("health", cmd_health))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # 봇 명령어 메뉴 설정
    await application.bot.set_my_commands([
        BotCommand("start", "봇 시작"),
        BotCommand("help", "사용법"),
        BotCommand("agents", "에이전트 목록"),
        BotCommand("cost", "비용 현황"),
        BotCommand("health", "시스템 상태"),
    ])

    logger.info("텔레그램 봇 생성 완료")
    return application


def get_bridge() -> TelegramBridge | None:
    """현재 브릿지 인스턴스 반환 (이벤트 연동용)."""
    return _bridge
