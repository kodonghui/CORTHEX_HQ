"""
WebSocket + SSE 브로드캐스트 매니저.

모든 WebSocket/SSE 클라이언트 연결을 관리하고,
이벤트를 한 곳에서 브로드캐스트합니다.

사용법:
    from ws_manager import wm
    await wm.broadcast("event_name", {"key": "value"})
    await wm.broadcast_multi([("event1", data1), ("event2", data2)])
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("corthex.ws")

# 한국 시간대 (KST, UTC+9)
_KST = timezone(timedelta(hours=9))


class ConnectionManager:
    """WebSocket + SSE 연결 관리 + 브로드캐스트 헬퍼."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._sse_queues: list[asyncio.Queue] = []

    # ── WebSocket 연결 관리 ──

    async def connect(self, ws: WebSocket) -> None:
        """WebSocket 연결 수락 + 목록에 추가."""
        await ws.accept()
        self._connections.append(ws)
        logger.info("WebSocket 연결됨 (총 %d)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        """WebSocket 연결 제거."""
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info("WebSocket 해제됨 (총 %d)", len(self._connections))

    @property
    def clients(self) -> list[WebSocket]:
        """현재 연결된 WebSocket 클라이언트 목록 (읽기 전용 복사본)."""
        return self._connections[:]

    @property
    def client_count(self) -> int:
        return len(self._connections)

    # ── WebSocket 브로드캐스트 ──

    async def broadcast(self, event: str, data: Any = None) -> None:
        """모든 WebSocket 클라이언트에게 이벤트 전송. 실패한 연결은 자동 제거."""
        if not self._connections:
            return
        message = {"event": event, "data": data}
        dead: list[WebSocket] = []
        for ws in self._connections[:]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_multi(self, events: list[tuple[str, Any]]) -> None:
        """여러 이벤트를 한 번에 브로드캐스트. [(event, data), ...] 형태."""
        if not self._connections or not events:
            return
        dead: list[WebSocket] = []
        for ws in self._connections[:]:
            try:
                for event, data in events:
                    await ws.send_json({"event": event, "data": data})
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    # ── SSE 관리 ──

    def add_sse_client(self, queue: asyncio.Queue) -> None:
        """SSE 클라이언트 큐 추가."""
        self._sse_queues.append(queue)

    def remove_sse_client(self, queue: asyncio.Queue) -> None:
        """SSE 클라이언트 큐 제거."""
        if queue in self._sse_queues:
            self._sse_queues.remove(queue)

    @property
    def sse_clients(self) -> list[asyncio.Queue]:
        """현재 연결된 SSE 클라이언트 큐 목록."""
        return self._sse_queues[:]

    async def broadcast_sse(self, msg_data: dict) -> None:
        """모든 SSE 클라이언트에게 메시지 전송."""
        for q in self._sse_queues[:]:
            try:
                await q.put(msg_data)
            except Exception:
                pass

    # ── 편의 메서드 (자주 쓰는 이벤트) ──

    async def send_agent_status(
        self, agent_id: str, status: str, progress: float = 0, detail: str = "",
        **extra: Any,
    ) -> None:
        """에이전트 상태를 브로드캐스트 (프론트엔드 상태 표시등 제어)."""
        data = {
            "agent_id": agent_id,
            "status": status,
            "progress": progress,
            "detail": detail,
        }
        if extra:
            data.update(extra)
        await self.broadcast("agent_status", data)

    async def send_activity_log(self, log_entry: dict) -> None:
        """활동 로그 브로드캐스트."""
        await self.broadcast("activity_log", log_entry)

    async def send_cost_update(self, total_cost: float, total_tokens: int = 0) -> None:
        """비용 업데이트 브로드캐스트."""
        await self.broadcast("cost_update", {
            "total_cost": total_cost,
            "total_tokens": total_tokens,
        })

    async def send_delegation_log(self, log_data: dict) -> None:
        """위임 로그 브로드캐스트 (WebSocket + SSE)."""
        await self.broadcast("delegation_log_update", log_data)
        # SSE에도 전송
        await self.broadcast_sse({
            "id": f"dl_{log_data.get('id', '')}",
            "sender": log_data.get("sender", ""),
            "receiver": log_data.get("receiver", ""),
            "title": log_data.get("title", ""),
            "message": log_data.get("message", ""),
            "log_type": log_data.get("log_type", "delegation"),
            "tools_used": log_data.get("tools_used", []),
            "source": "delegation",
            "created_at": log_data.get("created_at", datetime.now(_KST).isoformat()),
        })


# ── 싱글턴 인스턴스 ──
wm = ConnectionManager()
