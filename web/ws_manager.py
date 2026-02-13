"""
WebSocket connection manager for real-time agent status updates.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("corthex.ws")

# 한국 시간대 (KST, UTC+9)
_KST = timezone(timedelta(hours=9))


class ConnectionManager:
    """Manages WebSocket connections for real-time CEO dashboard updates."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info("WebSocket 연결됨 (총 %d)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info("WebSocket 해제됨 (총 %d)", len(self._connections))

    async def broadcast(self, event: str, data: Any = None) -> None:
        """Send an event to all connected clients."""
        message = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_agent_status(
        self, agent_id: str, status: str, progress: float = 0, detail: str = ""
    ) -> None:
        await self.broadcast("agent_status", {
            "agent_id": agent_id,
            "status": status,
            "progress": progress,
            "detail": detail,
        })

    async def send_activity_log(self, agent_id: str, action: str) -> None:
        await self.broadcast("activity_log", {
            "agent_id": agent_id,
            "action": action,
            "time": datetime.now(_KST).strftime("%H:%M:%S"),
        })

    async def send_cost_update(self, total_cost: float, total_tokens: int) -> None:
        await self.broadcast("cost_update", {
            "total_cost": total_cost,
            "total_tokens": total_tokens,
        })

    async def send_error_alert(
        self, error_type: str, message: str, severity: str = "error"
    ) -> None:
        """Send error alert to all connected clients."""
        await self.broadcast("error_alert", {
            "error_type": error_type,
            "message": message,
            "severity": severity,
            "timestamp": datetime.now(_KST).isoformat(),
        })
