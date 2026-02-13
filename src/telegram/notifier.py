"""
텔레그램 프로액티브 알림 모듈.

CEO에게 자동으로 알림을 보내는 기능입니다:
  - SNS 발행 승인 요청 (인라인 버튼 포함)
  - 비용 경고 (예산 한도 초과 시)
  - 에러 알림 (시스템 오류 발생 시)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.telegram import formatter

if TYPE_CHECKING:
    from telegram import Bot

logger = logging.getLogger("corthex.telegram.notifier")


class TelegramNotifier:
    """CEO에게 텔레그램으로 자동 알림을 보내는 모듈."""

    def __init__(self, bot: Bot, ceo_chat_id: int) -> None:
        self.bot = bot
        self.ceo_chat_id = ceo_chat_id

    # ─── SNS 발행 승인 요청 ───

    async def notify_sns_approval(self, request_data: dict[str, Any]) -> None:
        """SNS 발행 승인 요청 알림.

        CEO의 텔레그램에 SNS 콘텐츠 미리보기와 승인/거절 인라인 버튼을 보냅니다.

        Args:
            request_data: SNS 발행 요청 데이터
                - request_id: 요청 고유 ID
                - platform: SNS 플랫폼 (instagram, twitter 등)
                - content: 발행할 콘텐츠 (title, body 등)
                - created_by: 요청한 에이전트 ID
        """
        request_id = request_data.get("request_id", "unknown")
        platform = request_data.get("platform", "알 수 없음")
        content = request_data.get("content", {})
        title = content.get("title", "(제목 없음)") if isinstance(content, dict) else str(content)[:100]
        body_preview = ""
        if isinstance(content, dict):
            body_preview = str(content.get("body", ""))[:300]
        created_by = request_data.get("created_by", "에이전트")

        text = (
            f"\U0001f514 *SNS 발행 승인 요청*\n"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            f"\U0001f4f1 플랫폼: {platform}\n"
            f"\U0001f464 요청자: {created_by}\n"
            f"\U0001f4dd 제목: {title}\n"
        )
        if body_preview:
            text += f"\n\U0001f4c4 내용 미리보기:\n{body_preview}"
            if len(str(content.get("body", ""))) > 300:
                text += "\n..."
        text += f"\n\n\U0001f194 요청 ID: `{request_id}`"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("\u2705 승인", callback_data=f"sns_approve:{request_id}"),
                InlineKeyboardButton("\u274c 거절", callback_data=f"sns_reject:{request_id}"),
            ]
        ])

        try:
            await self.bot.send_message(
                chat_id=self.ceo_chat_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
            logger.info("SNS 승인 요청 알림 전송: %s (%s)", request_id, platform)
        except Exception as e:
            logger.error("SNS 승인 알림 전송 실패: %s", e)

    # ─── 비용 경고 ───

    async def notify_cost_alert(
        self,
        current_cost: float,
        budget_limit: float,
        detail: str = "",
    ) -> None:
        """비용 경고 알림.

        현재 비용이 예산 한도의 일정 비율을 넘었을 때 CEO에게 경고합니다.

        Args:
            current_cost: 현재 누적 비용 (USD)
            budget_limit: 예산 한도 (USD)
            detail: 추가 설명
        """
        pct = (current_cost / budget_limit * 100) if budget_limit > 0 else 0

        if pct >= 100:
            icon = "\U0001f534"  # 🔴
            level = "한도 초과"
        elif pct >= 80:
            icon = "\U0001f7e1"  # 🟡
            level = "주의"
        else:
            icon = "\U0001f7e2"  # 🟢
            level = "정상"

        text = (
            f"{icon} *비용 경고: {level}*\n"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            f"\U0001f4b0 현재 비용: ${current_cost:.4f}\n"
            f"\U0001f3af 예산 한도: ${budget_limit:.2f}\n"
            f"\U0001f4ca 사용률: {pct:.1f}%\n"
        )
        if detail:
            text += f"\n{detail}"

        try:
            await self.bot.send_message(
                chat_id=self.ceo_chat_id,
                text=text,
                parse_mode="Markdown",
            )
            logger.info("비용 경고 알림 전송: $%.4f / $%.2f (%.1f%%)", current_cost, budget_limit, pct)
        except Exception as e:
            logger.error("비용 경고 알림 전송 실패: %s", e)

    # ─── 에러 알림 ───

    async def notify_error(
        self,
        error_source: str,
        error_message: str,
        detail: str = "",
    ) -> None:
        """시스템 에러 알림.

        심각한 에러 발생 시 CEO에게 즉시 알림을 보냅니다.

        Args:
            error_source: 에러가 발생한 곳 (에이전트 ID, 모듈명 등)
            error_message: 에러 메시지
            detail: 추가 설명
        """
        text = (
            f"\U0001f6a8 *시스템 에러 알림*\n"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            f"\U0001f4cd 발생 위치: {error_source}\n"
            f"\u274c 오류: {error_message[:500]}\n"
        )
        if detail:
            text += f"\n\U0001f4cb 상세:\n{detail[:500]}"

        try:
            await self.bot.send_message(
                chat_id=self.ceo_chat_id,
                text=text,
                parse_mode="Markdown",
            )
            logger.info("에러 알림 전송: %s", error_source)
        except Exception as e:
            logger.error("에러 알림 전송 실패: %s", e)
