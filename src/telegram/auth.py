"""
CEO 인증 모듈.

TELEGRAM_CEO_CHAT_ID 환경변수로 CEO만 명령을 보낼 수 있도록 제한합니다.
미설정 시 /start를 보내면 chat_id를 로그에 표시하여 설정을 돕습니다.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("corthex.telegram.auth")


class TelegramAuth:
    """chat_id 기반 CEO 인증."""

    def __init__(self) -> None:
        raw = os.getenv("TELEGRAM_CEO_CHAT_ID", "").strip()
        self._ceo_chat_id: int | None = int(raw) if raw else None
        if self._ceo_chat_id:
            logger.info("텔레그램 CEO chat_id 설정됨: %d", self._ceo_chat_id)
        else:
            logger.warning(
                "TELEGRAM_CEO_CHAT_ID 미설정. "
                "봇에 /start를 보내면 chat_id가 로그에 표시됩니다."
            )

    @property
    def is_configured(self) -> bool:
        return self._ceo_chat_id is not None

    def is_authorized(self, chat_id: int) -> bool:
        if self._ceo_chat_id is None:
            return False
        return chat_id == self._ceo_chat_id

    def get_setup_message(self, chat_id: int) -> str:
        """미설정 시 chat_id 안내 메시지."""
        logger.info("텔레그램 chat_id 감지: %d — .env.local에 설정하세요.", chat_id)
        return (
            f"CORTHEX HQ 텔레그램 봇입니다.\n\n"
            f"당신의 chat_id: `{chat_id}`\n\n"
            f".env.local 파일에 아래를 추가한 뒤 서버를 재시작하세요:\n"
            f"`TELEGRAM_CEO_CHAT_ID={chat_id}`"
        )
