"""
SNS Webhook 수신기.

각 플랫폼으로부터 실시간 알림을 받아 처리합니다.
- YouTube: 신규 댓글, 구독자 알림
- Instagram: 댓글, 멘션 알림
- LinkedIn: 댓글, 반응 알림
- Tistory: 방명록, 댓글 알림 (커스텀 폴링)

Webhook은 "우리가 물어보는 게 아니라 상대방이 알려주는 것"
→ 플랫폼에서 이벤트가 발생하면, 우리 서버의 /webhook/{platform} 으로 POST 요청이 옴
→ 그 요청을 파싱해서 내부 에이전트에게 전달
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Callable, Awaitable

logger = logging.getLogger("corthex.sns.webhook")


class WebhookEvent:
    """파싱된 Webhook 이벤트 데이터."""

    def __init__(
        self,
        platform: str,
        event_type: str,
        data: dict[str, Any],
        raw_body: str = "",
        received_at: float = 0,
    ) -> None:
        self.platform = platform
        self.event_type = event_type
        self.data = data
        self.raw_body = raw_body
        self.received_at = received_at or time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "event_type": self.event_type,
            "data": self.data,
            "received_at": self.received_at,
        }


# 이벤트 핸들러 타입: async (WebhookEvent) -> None
EventHandler = Callable[[WebhookEvent], Awaitable[None]]


class WebhookReceiver:
    """플랫폼별 Webhook 수신 및 이벤트 디스패치."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}
        self._event_log: list[dict[str, Any]] = []

    def on(self, event_type: str, handler: EventHandler) -> None:
        """이벤트 핸들러 등록. event_type 예: 'youtube.comment', 'instagram.mention'"""
        self._handlers.setdefault(event_type, []).append(handler)

    async def _dispatch(self, event: WebhookEvent) -> None:
        key = f"{event.platform}.{event.event_type}"
        self._event_log.append(event.to_dict())

        handlers = self._handlers.get(key, []) + self._handlers.get("*", [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error("Webhook 핸들러 오류 [%s]: %s", key, e)

    # ── 플랫폼별 파서 ──

    async def handle_youtube(
        self, body: bytes, headers: dict[str, str],
    ) -> dict[str, str]:
        """YouTube PubSubHubbub Webhook 처리."""
        # YouTube는 Atom XML로 알림이 옴
        content = body.decode("utf-8")

        # 구독 검증 (hub.challenge)
        # 실제로는 GET 요청으로 오지만, 여기서는 POST 파싱만 처리

        event = WebhookEvent(
            platform="youtube",
            event_type="notification",
            data={"raw_xml": content},
            raw_body=content,
        )
        await self._dispatch(event)
        return {"status": "ok"}

    async def handle_instagram(
        self, body: bytes, headers: dict[str, str],
    ) -> dict[str, str]:
        """Instagram Webhook 처리."""
        # 서명 검증
        signature = headers.get("x-hub-signature-256", "")
        app_secret = os.getenv("INSTAGRAM_APP_SECRET", "")
        if app_secret and signature:
            expected = "sha256=" + hmac.new(
                app_secret.encode(), body, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                logger.warning("[Instagram] Webhook 서명 불일치")
                return {"status": "invalid_signature"}

        data = json.loads(body)

        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                event = WebhookEvent(
                    platform="instagram",
                    event_type=change.get("field", "unknown"),
                    data=change.get("value", {}),
                    raw_body=body.decode("utf-8"),
                )
                await self._dispatch(event)

        return {"status": "ok"}

    async def handle_linkedin(
        self, body: bytes, headers: dict[str, str],
    ) -> dict[str, str]:
        """LinkedIn Webhook 처리."""
        data = json.loads(body)

        event = WebhookEvent(
            platform="linkedin",
            event_type=data.get("eventType", "unknown"),
            data=data,
            raw_body=body.decode("utf-8"),
        )
        await self._dispatch(event)
        return {"status": "ok"}

    async def handle_tistory(
        self, body: bytes, headers: dict[str, str],
    ) -> dict[str, str]:
        """Tistory 커스텀 Webhook/폴링 결과 처리.
        Tistory는 공식 Webhook이 없으므로, 주기적 폴링 결과를 이 포맷으로 처리합니다.
        """
        data = json.loads(body)

        event = WebhookEvent(
            platform="tistory",
            event_type=data.get("type", "poll_result"),
            data=data,
            raw_body=body.decode("utf-8"),
        )
        await self._dispatch(event)
        return {"status": "ok"}

    # ── 이벤트 로그 ──

    def recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._event_log[-limit:]
