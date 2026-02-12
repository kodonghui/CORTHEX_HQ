"""
Telegram Bot integration for CORTHEX HQ.

CEO가 아이폰/아이패드의 텔레그램 앱에서 명령을 보내고 결과를 받을 수 있다.
Polling 방식으로 동작하므로 공개 URL(webhook)이 필요 없다.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

logger = logging.getLogger("corthex.telegram")

# python-telegram-bot이 설치되어 있을 때만 동작
try:
    from telegram import Bot, Update
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        ContextTypes,
        filters,
    )
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False
    logger.info("python-telegram-bot 미설치 — 텔레그램 봇 비활성화")


class CorthexTelegramBot:
    """CORTHEX HQ 텔레그램 봇. CEO만 사용 가능."""

    def __init__(
        self,
        token: str,
        allowed_chat_id: str,
        command_callback: Any = None,
    ) -> None:
        """
        Args:
            token: 텔레그램 봇 토큰 (BotFather에서 발급)
            allowed_chat_id: 허용된 채팅 ID (CEO 본인만)
            command_callback: async func(text, depth, use_batch) -> dict
        """
        if not HAS_TELEGRAM:
            raise ImportError("python-telegram-bot 패키지를 설치하세요: pip install python-telegram-bot")

        self.token = token
        self.allowed_chat_id = str(allowed_chat_id)
        self.command_callback = command_callback
        self._app: Optional[Application] = None

    async def start(self) -> None:
        """봇 시작 (polling 방식)."""
        self._app = Application.builder().token(self.token).build()
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("batch", self._cmd_batch))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        logger.info("텔레그램 봇 시작됨 (polling)")

    async def stop(self) -> None:
        """봇 정지."""
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    def _check_auth(self, update: Update) -> bool:
        """CEO 인증 확인."""
        chat_id = str(update.effective_chat.id)
        if chat_id != self.allowed_chat_id:
            logger.warning("미인증 접근 시도: chat_id=%s", chat_id)
            return False
        return True

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """'/start' 명령 처리."""
        if not self._check_auth(update):
            await update.message.reply_text("인증되지 않은 접근입니다.")
            return
        await update.message.reply_text(
            "CORTHEX HQ 연결됨.\n\n"
            "명령어를 입력하면 비서실장에게 전달됩니다.\n"
            "/batch <명령> — 절약 모드 (50% 할인)\n"
            "/status — 시스템 상태 확인"
        )

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """'/status' 명령 처리."""
        if not self._check_auth(update):
            return
        await update.message.reply_text("CORTHEX HQ 온라인.")

    async def _cmd_batch(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """'/batch <명령>' — 절약 모드로 명령 실행."""
        if not self._check_auth(update):
            return
        text = " ".join(context.args) if context.args else ""
        if not text:
            await update.message.reply_text("사용법: /batch <명령>")
            return
        await self._execute_command(update, text, use_batch=True)

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """일반 텍스트 메시지 → CORTHEX 명령."""
        if not self._check_auth(update):
            return
        text = update.message.text.strip()
        if not text:
            return
        await self._execute_command(update, text, use_batch=False)

    async def _execute_command(self, update: Update, text: str, use_batch: bool = False) -> None:
        """명령 실행 + 결과 전송."""
        mode_label = "절약" if use_batch else "실시간"
        await update.message.reply_text(f"작업 접수됨 ({mode_label} 모드)")

        if not self.command_callback:
            await update.message.reply_text("명령 처리 콜백이 설정되지 않았습니다.")
            return

        try:
            result = await self.command_callback(text, depth=3, use_batch=use_batch)
            result_text = str(result.get("result_data", result.get("summary", "결과 없음")))
            await self._send_long_message(update.effective_chat.id, result_text)
        except Exception as e:
            await update.message.reply_text(f"오류: {e}")

    async def _send_long_message(self, chat_id: int, text: str) -> None:
        """텔레그램 4096자 제한 → 자동 분할 전송."""
        bot = self._app.bot
        max_len = 4000
        for i in range(0, len(text), max_len):
            chunk = text[i:i + max_len]
            await bot.send_message(chat_id, chunk)
