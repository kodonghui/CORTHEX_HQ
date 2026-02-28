"""
CORTHEX HQ - Telegram Bot.

CEO가 텔레그램에서 업무 지시를 내리고 보고서를 받을 수 있는 봇입니다.
FastAPI 서버의 asyncio 이벤트 루프 안에서 polling 방식으로 동작합니다.

명령어:
  /start    - 봇 시작 (chat_id 안내)
  /help     - 사용법
  /agents   - 에이전트 목록
  /cost     - 비용 현황
  /health   - 시스템 상태
  /detail   - 마지막 보고서 전체 보기
  /tasks    - 최근 작업 목록
  /task ID  - 특정 작업 상세 보기
  /result ID - 작업 결과 조회 (/task 별칭)
  /cancel ID - 작업 취소
  /last     - 마지막 작업 결과 보기
  /status   - 현재 실행 중인 작업 목록
  /models   - 사용 가능한 모델 목록
  (일반 텍스트) - CEO 업무 지시 (한국어 '토론 주제' 포함)
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from src.telegram.auth import TelegramAuth
from src.telegram.bridge import TelegramBridge
from src.telegram import formatter

if TYPE_CHECKING:
    from src.core.context import SharedContext
    from src.core.orchestrator import Orchestrator
    from src.core.registry import AgentRegistry
    from src.core.task_store import TaskStore
    from src.llm.router import ModelRouter
    from web.ws_manager import ConnectionManager

logger = logging.getLogger("corthex.telegram.bot")

# 모듈 레벨 참조 (핸들러에서 사용)
_auth: TelegramAuth | None = None
_bridge: TelegramBridge | None = None
_registry: AgentRegistry | None = None
_model_router: ModelRouter | None = None
_task_store: TaskStore | None = None
_notifier: object | None = None  # TelegramNotifier (순환 import 방지)


# ─── Command Handlers (기존) ───


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
        "*CORTHEX HQ \uc0ac\uc6a9\ubc95*\n\n"
        "*\uc5c5\ubb34 \uc9c0\uc2dc*: \uadf8\ub0e5 \uba54\uc2dc\uc9c0\ub97c \ubcf4\ub0b4\uba74 \ub429\ub2c8\ub2e4\n"
        "  \uc608: `\uc0bc\uc131\uc804\uc790 \ud22c\uc790 \ubd84\uc11d\ud574\uc918`\n"
        "  \uc608: `\ub9ac\ud2b8\ub9c8\uc2a4\ud130 \uacbd\uc7c1\uc0ac \ud604\ud669 \uc815\ub9ac\ud574\uc918`\n\n"
        "*\uad00\ub9ac \uba85\ub839\uc5b4*:\n"
        "  /agents  - \uc5d0\uc774\uc804\ud2b8 \ubaa9\ub85d\n"
        "  /cost    - \ube44\uc6a9 \ud604\ud669\n"
        "  /health  - \uc2dc\uc2a4\ud15c \uc0c1\ud0dc\n"
        "  /models  - \uc0ac\uc6a9 \uac00\ub2a5\ud55c AI \ubaa8\ub378\n\n"
        "*\uc791\uc5c5 \uba85\ub839\uc5b4*:\n"
        "  /status  - \uc2e4\ud589 \uc911\uc778 \uc791\uc5c5 \ubaa9\ub85d\n"
        "  /tasks   - \ucd5c\uadfc \uc791\uc5c5 \ubaa9\ub85d\n"
        "  /last    - \ub9c8\uc9c0\ub9c9 \uc791\uc5c5 \uacb0\uacfc\n"
        "  /result ID - \uc791\uc5c5 \uacb0\uacfc \uc870\ud68c\n"
        "  /cancel ID - \uc791\uc5c5 \ucde8\uc18c\n\n"
        "*\ubcf4\uace0\uc11c \uba85\ub839\uc5b4*:\n"
        "  /detail  - \ub9c8\uc9c0\ub9c9 \ubcf4\uace0\uc11c \uc804\uccb4 \ubcf4\uae30\n"
        "  /task ID - \ud2b9\uc815 \uc791\uc5c5 \uc0c1\uc138 \ubcf4\uae30\n\n"
        "*\ud1a0\ub860 \uae30\ub2a5*:\n"
        "  `\ud1a0\ub860 [\uc8fc\uc81c]` - \uc5ec\ub7ec AI\uac00 \ud1a0\ub860",
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


# ─── 새 명령어: 보고서 ───


async def cmd_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/detail - 마지막 보고서 전체 보기."""
    if not _is_ceo(update) or not _bridge:
        return

    if not _bridge._last_full_report:
        await update.message.reply_text(
            "\U0001f4cb 상세 보고서가 없습니다.\n먼저 업무를 지시해주세요."
        )
        return

    messages = formatter._split_message(_bridge._last_full_report)
    for msg in messages:
        await update.message.reply_text(msg, parse_mode="Markdown")
        await asyncio.sleep(0.3)


async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/tasks - 최근 작업 목록."""
    if not _is_ceo(update) or not _task_store:
        await update.message.reply_text(
            "\U0001f4cb 작업 저장소가 초기화되지 않았습니다."
        )
        return

    tasks = _task_store.list_all(limit=10)
    text = formatter.format_task_list(tasks)
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_task_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/task ID - 특정 작업 상세 보기."""
    if not _is_ceo(update) or not _task_store:
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "사용법: /task [작업ID]\n\n"
            "/tasks 명령어로 작업 ID를 먼저 확인하세요."
        )
        return

    task = _task_store.get(args[0])
    if not task:
        await update.message.reply_text(f"\u274c 작업 ID '{args[0]}'을 찾을 수 없습니다.")
        return

    messages = formatter.format_task_detail(task)
    for msg in messages:
        await update.message.reply_text(msg, parse_mode="Markdown")
        await asyncio.sleep(0.3)


# ─── 새 명령어: 작업 관리 ───


async def cmd_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/result [작업ID] - 작업 결과 조회 (/task 별칭)."""
    await cmd_task_detail(update, context)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/cancel [작업ID] - 작업 취소."""
    if not _is_ceo(update) or not _task_store:
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "\uc0ac\uc6a9\ubc95: /cancel [\uc791\uc5c5ID]\n\n"
            "/tasks \uba85\ub839\uc5b4\ub85c \uc791\uc5c5 ID\ub97c \uba3c\uc800 \ud655\uc778\ud558\uc138\uc694."
        )
        return

    task = _task_store.get(args[0])
    if not task:
        await update.message.reply_text(f"\u274c \uc791\uc5c5 ID '{args[0]}'\uc744 \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.")
        return

    status_val = task.status.value if hasattr(task.status, "value") else str(task.status)
    if status_val in ("completed", "failed", "cancelled"):
        await update.message.reply_text(
            f"\u274c \uc774\ubbf8 \uc885\ub8cc\ub41c \uc791\uc5c5\uc785\ub2c8\ub2e4. (\uc0c1\ud0dc: {status_val})"
        )
        return

    try:
        _task_store.update_status(args[0], "cancelled")
        await update.message.reply_text(
            f"\u2705 \uc791\uc5c5 `{args[0]}` \ucde8\uc18c \uc644\ub8cc.",
            parse_mode="Markdown",
        )
    except Exception as e:
        await update.message.reply_text(f"\u274c \ucde8\uc18c \uc2e4\ud328: {e}")


async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/last - 마지막 작업 결과 보기."""
    if not _is_ceo(update) or not _task_store:
        await update.message.reply_text(
            "\U0001f4cb \uc791\uc5c5 \uc800\uc7a5\uc18c\uac00 \ucd08\uae30\ud654\ub418\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4."
        )
        return

    tasks = _task_store.list_all(limit=1)
    if not tasks:
        await update.message.reply_text("\U0001f4cb \uc791\uc5c5 \uae30\ub85d\uc774 \uc5c6\uc2b5\ub2c8\ub2e4.")
        return

    task = tasks[0]
    messages = formatter.format_task_detail(task)
    for msg in messages:
        await update.message.reply_text(msg, parse_mode="Markdown")
        await asyncio.sleep(0.3)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/status - 현재 실행 중인 작업 목록."""
    if not _is_ceo(update) or not _task_store:
        await update.message.reply_text(
            "\U0001f4cb \uc791\uc5c5 \uc800\uc7a5\uc18c\uac00 \ucd08\uae30\ud654\ub418\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4."
        )
        return

    all_tasks = _task_store.list_all(limit=50)
    running = [t for t in all_tasks
               if (t.status.value if hasattr(t.status, "value") else str(t.status))
               in ("running", "pending", "queued")]
    text = formatter.format_running_tasks(running)
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/models - 사용 가능한 모델 목록."""
    if not _is_ceo(update):
        return
    text = formatter.format_models_list()
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── 토론 기능 ───


async def _run_debate(update: Update, topic: str) -> None:
    """여러 AI 모델로 토론을 진행하고 결과를 전송."""
    # 토론에 참여할 모델 3개 (각 프로바이더에서 1개씩)
    debate_models = [
        "claude-sonnet-4-6",
        "gpt-5.2",
        "gemini-2.5-pro",
    ]

    # 시작 알림
    start_msg = formatter.format_debate_start(topic, debate_models)
    status = await update.message.reply_text(start_msg, parse_mode="Markdown")

    opinions: list[dict] = []

    if _bridge and _bridge.orchestrator:
        # Orchestrator를 통해 각 모델에 의견 요청
        for model_id in debate_models:
            try:
                result = await _bridge.orchestrator.process_command(
                    f"[{model_id}] \ub2e4\uc74c \uc8fc\uc81c\uc5d0 \ub300\ud574 \ub2f9\uc2e0\uc758 \uc758\uacac\uc744 "
                    f"300\uc790 \uc774\ub0b4\ub85c \ub9d0\ud574\uc8fc\uc138\uc694: {topic}"
                )
                opinion_text = str(result.result_data or result.summary or "(\uc751\ub2f5 \uc5c6\uc74c)")
                opinions.append({"model": model_id, "opinion": opinion_text})
            except Exception as e:
                opinions.append({"model": model_id, "opinion": f"(\uc624\ub958: {e})"})
    else:
        # Orchestrator 없으면 안내 메시지
        for model_id in debate_models:
            opinions.append({
                "model": model_id,
                "opinion": "(\uc2dc\uc2a4\ud15c\uc774 \ucd08\uae30\ud654\ub418\uc9c0 \uc54a\uc544 \ud1a0\ub860\uc744 \uc9c4\ud589\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4)"
            })

    # 상태 메시지 삭제
    try:
        await status.delete()
    except Exception:
        pass

    # 결과 전송
    messages = formatter.format_debate_result(topic, opinions)
    for msg in messages:
        await update.message.reply_text(msg, parse_mode="Markdown")
        await asyncio.sleep(0.3)


# ─── SNS 승인/거절 인라인 버튼 처리 ───


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """인라인 버튼 콜백 처리 (SNS 승인/거절 등)."""
    query = update.callback_query
    if not query or not _auth:
        return

    if not _auth.is_authorized(query.from_user.id):
        await query.answer("권한이 없습니다.")
        return

    data = query.data or ""

    if data.startswith("sns_approve:"):
        request_id = data.split(":", 1)[1]
        try:
            from web.app import tool_pool_ref
            if tool_pool_ref:
                result = await tool_pool_ref.invoke(
                    "sns_manager", action="approve", request_id=request_id,
                )
                # 자동 발행 트리거 — 웹 승인과 동일한 동작
                if "error" not in result:
                    from web.handlers.sns_handler import _auto_publish_after_approve
                    asyncio.create_task(_auto_publish_after_approve(request_id))
                await query.answer("승인 완료!")
                await query.edit_message_text(
                    f"\u2705 *SNS 발행 승인 완료*\n요청 ID: `{request_id}`\n\U0001f680 자동 발행 진행중...",
                    parse_mode="Markdown",
                )
            else:
                await query.answer("시스템이 초기화되지 않았습니다.")
        except Exception as e:
            await query.answer(f"오류: {e}")
            logger.error("SNS 승인 처리 실패: %s", e)

    elif data.startswith("sns_reject:"):
        request_id = data.split(":", 1)[1]
        try:
            from web.app import tool_pool_ref
            if tool_pool_ref:
                await tool_pool_ref.invoke(
                    "sns_manager", action="reject",
                    request_id=request_id, reason="CEO 텔레그램에서 거절",
                )
                await query.answer("거절 완료!")
                await query.edit_message_text(
                    f"\u274c *SNS 발행 거절*\n요청 ID: `{request_id}`",
                    parse_mode="Markdown",
                )
            else:
                await query.answer("시스템이 초기화되지 않았습니다.")
        except Exception as e:
            await query.answer(f"오류: {e}")
            logger.error("SNS 거절 처리 실패: %s", e)


# ─── 일반 메시지 (CEO 업무 지시) ───


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """일반 텍스트 = CEO 업무 지시. 한국어 명령어도 처리."""
    if not _is_ceo(update) or not _bridge:
        return

    text = update.message.text.strip()
    if not text:
        return

    # 한국어 "토론" 명령어 처리
    if text.startswith("토론 ") or text.startswith("/토론 "):
        topic = text.split(" ", 1)[1] if " " in text else ""
        if topic:
            asyncio.create_task(_run_debate(update, topic))
            return
        else:
            await update.message.reply_text(
                "\uc0ac\uc6a9\ubc95: \ud1a0\ub860 [\uc8fc\uc81c]\n\n"
                "\uc608: `\ud1a0\ub860 AI\uac00 \uc778\uac04\uc758 \uc77c\uc790\ub9ac\ub97c \ub300\uccb4\ud560\uae4c?`",
                parse_mode="Markdown",
            )
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
    context: SharedContext | None = None,
    task_store: TaskStore | None = None,
) -> Application:
    """텔레그램 봇 Application을 생성하고 반환합니다."""
    global _auth, _bridge, _registry, _model_router, _task_store, _notifier

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")

    _auth = TelegramAuth()
    _registry = registry
    _model_router = model_router
    _task_store = task_store

    # Application 생성
    application = Application.builder().token(token).build()

    # 브릿지 생성 (auth가 설정된 경우에만)
    if _auth.is_configured:
        ceo_chat_id = int(os.getenv("TELEGRAM_CEO_CHAT_ID", "0"))
        _bridge = TelegramBridge(
            bot=application.bot,
            orchestrator=orchestrator,
            ws_manager=ws_manager,
            model_router=model_router,
            registry=registry,
            ceo_chat_id=ceo_chat_id,
            context=context,
            task_store=task_store,
        )

        # Notifier 생성 (SNS 승인 알림용)
        try:
            from src.telegram.notifier import TelegramNotifier
            _notifier = TelegramNotifier(bot=application.bot, ceo_chat_id=ceo_chat_id)
            logger.info("텔레그램 알림 모듈 초기화 완료")
        except Exception as e:
            logger.warning("텔레그램 알림 모듈 초기화 실패 (무시): %s", e)

    # 핸들러 등록 — 기존
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("agents", cmd_agents))
    application.add_handler(CommandHandler("cost", cmd_cost))
    application.add_handler(CommandHandler("health", cmd_health))

    # 핸들러 등록 — 보고서 명령어
    application.add_handler(CommandHandler("detail", cmd_detail))
    application.add_handler(CommandHandler("tasks", cmd_tasks))
    application.add_handler(CommandHandler("task", cmd_task_detail))

    # 핸들러 등록 — 작업 관리 명령어
    application.add_handler(CommandHandler("result", cmd_result))
    application.add_handler(CommandHandler("cancel", cmd_cancel))
    application.add_handler(CommandHandler("last", cmd_last))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("models", cmd_models))

    # 인라인 버튼 콜백 (SNS 승인/거절)
    application.add_handler(CallbackQueryHandler(handle_callback))

    # 일반 텍스트 메시지 (항상 마지막에 등록 — 한국어 "토론" 처리 포함)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # 봇 명령어 메뉴 설정
    await application.bot.set_my_commands([
        BotCommand("start", "\ubd07 \uc2dc\uc791"),
        BotCommand("help", "\uc0ac\uc6a9\ubc95"),
        BotCommand("agents", "\uc5d0\uc774\uc804\ud2b8 \ubaa9\ub85d"),
        BotCommand("cost", "\ube44\uc6a9 \ud604\ud669"),
        BotCommand("health", "\uc2dc\uc2a4\ud15c \uc0c1\ud0dc"),
        BotCommand("detail", "\ub9c8\uc9c0\ub9c9 \ubcf4\uace0\uc11c \uc804\uccb4 \ubcf4\uae30"),
        BotCommand("tasks", "\ucd5c\uadfc \uc791\uc5c5 \ubaa9\ub85d"),
        BotCommand("task", "\ud2b9\uc815 \uc791\uc5c5 \uc0c1\uc138 \ubcf4\uae30"),
        BotCommand("result", "\uc791\uc5c5 \uacb0\uacfc \uc870\ud68c"),
        BotCommand("cancel", "\uc791\uc5c5 \ucde8\uc18c"),
        BotCommand("last", "\ub9c8\uc9c0\ub9c9 \uc791\uc5c5 \uacb0\uacfc"),
        BotCommand("status", "\uc2e4\ud589 \uc911\uc778 \uc791\uc5c5"),
        BotCommand("models", "\uc0ac\uc6a9 \uac00\ub2a5\ud55c \ubaa8\ub378 \ubaa9\ub85d"),
    ])

    logger.info("\ud154\ub808\uadf8\ub7a8 \ubd07 \uc0dd\uc131 \uc644\ub8cc (\uba85\ub839\uc5b4 13\uac1c \ub4f1\ub85d)")
    return application


def get_bridge() -> TelegramBridge | None:
    """현재 브릿지 인스턴스 반환 (이벤트 연동용)."""
    return _bridge


def get_notifier():
    """현재 Notifier 인스턴스 반환 (SNS 승인 알림용)."""
    return _notifier
