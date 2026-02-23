"""활동 로그 · 위임 로그 · 내부통신(Comms) API.

비유: 관제탑 — 에이전트 간 위임, 협업, 내부 메시지를 기록하고 실시간 중계.
"""
import asyncio
import json
import logging
import sqlite3
import time as _time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from db import (
    list_activity_logs,
    save_activity_log,
    get_connection,
)
from ws_manager import wm

logger = logging.getLogger("corthex")

router = APIRouter(tags=["activity", "comms"])


# ── 활동 로그 API ──

@router.get("/api/activity-logs")
async def get_activity_logs(limit: int = 50, agent_id: str = None):
    logs = list_activity_logs(limit=limit, agent_id=agent_id)
    return logs


# ── 협업 로그 API ──

@router.get("/api/delegation-log")
async def get_delegation_log(agent: str = None, division: str = None, limit: int = 100):
    """에이전트 간 위임/협업 로그를 조회합니다.

    ?agent=비서실장 — 특정 에이전트 관련 로그만 반환
    ?division=cio  — 해당 처 팀 전체 관련 로그 반환 (cio/cto/cmo/cso/clo/cpo)
    """
    try:
        from db import list_delegation_logs

        if division:
            # 처별 키워드 매핑 (sender/receiver LIKE 검색)
            _div_keywords: dict[str, list[str]] = {
                "cio": ["CIO", "투자분석", "stock_analysis", "market_condition", "technical_analysis", "risk_management"],
                "cto": ["CTO", "기술개발", "frontend", "backend", "infra", "ai_model"],
                "cmo": ["CMO", "마케팅", "survey", "content_spec", "community"],
                "cso": ["CSO", "사업기획", "business_plan", "market_research", "financial_model"],
                "clo": ["CLO", "법무", "copyright", "patent"],
                "cpo": ["CPO", "출판", "chronicle", "editor_spec", "archive"],
            }
            keywords = _div_keywords.get(division.lower(), [])
            if not keywords:
                return []
            conn = get_connection()
            try:
                placeholders = " OR ".join(["sender LIKE ? OR receiver LIKE ?" for _ in keywords])
                params = []
                for k in keywords:
                    params.extend([f"%{k}%", f"%{k}%"])
                params.append(limit)
                rows = conn.execute(
                    f"SELECT id, sender, receiver, message, task_id, log_type, tools_used, created_at "
                    f"FROM delegation_log WHERE ({placeholders}) "
                    f"ORDER BY created_at DESC LIMIT ?",
                    params,
                ).fetchall()
                return [dict(r) for r in rows]
            except sqlite3.OperationalError:
                return []
            finally:
                conn.close()
        else:
            logs = list_delegation_logs(agent=agent, limit=limit)
            return logs
    except Exception:
        return []


@router.post("/api/delegation-log")
async def post_delegation_log(request: Request):
    """에이전트 간 위임/협업 로그를 저장합니다.

    body: {sender, receiver, message, task_id?, log_type?}
    """
    try:
        from db import save_delegation_log
        body = await request.json()
        sender = body.get("sender", "")
        receiver = body.get("receiver", "")
        message = body.get("message", "")
        if not sender or not receiver or not message:
            return {"success": False, "error": "sender, receiver, message는 필수입니다."}
        row_id = save_delegation_log(
            sender=sender,
            receiver=receiver,
            message=message,
            task_id=body.get("task_id"),
            log_type=body.get("log_type", "delegation"),
        )
        # WebSocket 실시간 broadcast — 열려있는 모든 클라이언트에 즉시 전달
        _log_data = {
            "id": row_id,
            "sender": sender,
            "receiver": receiver,
            "message": message,
            "log_type": body.get("log_type", "delegation"),
            "created_at": _time.time(),
        }
        await wm.send_delegation_log(_log_data)
        return {"success": True, "id": row_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── 내부통신 통합 API (delegation_log + cross_agent_messages 통합) ──

@router.get("/api/comms/messages")
async def get_comms_messages(limit: int = 100, msg_type: str = ""):
    """내부통신 통합 메시지 조회 — delegation_log + cross_agent_messages 병합."""
    try:
        conn = get_connection()
        messages = []

        # 1) delegation_log
        try:
            rows = conn.execute(
                "SELECT id, sender, receiver, message, log_type, tools_used, created_at "
                "FROM delegation_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            for r in rows:
                lt = r["log_type"] or "delegation"
                if msg_type and lt != msg_type:
                    continue
                _tu = r["tools_used"] or ""
                _tools_list = [t.strip() for t in _tu.split(",") if t.strip()] if _tu else []
                messages.append({
                    "id": f"dl_{r['id']}",
                    "sender": r["sender"],
                    "receiver": r["receiver"],
                    "message": r["message"],
                    "log_type": lt,
                    "tools_used": _tools_list,
                    "source": "delegation",
                    "created_at": r["created_at"],
                })
        except Exception as e:
            logger.debug("위임 로그 조회 실패: %s", e)

        # 2) cross_agent_messages
        try:
            rows2 = conn.execute(
                "SELECT id, msg_type, from_agent, to_agent, data, status, created_at "
                "FROM cross_agent_messages ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            for r in rows2:
                try:
                    data = json.loads(r["data"]) if r["data"] else {}
                except Exception:
                    data = {}
                lt = r["msg_type"] or "p2p"
                if msg_type and lt != msg_type:
                    continue
                msg_text = data.get("task", data.get("message", data.get("next_task", "")))
                messages.append({
                    "id": f"ca_{r['id']}",
                    "sender": r["from_agent"],
                    "receiver": r["to_agent"],
                    "message": msg_text,
                    "log_type": lt,
                    "source": "cross_agent",
                    "status": r["status"],
                    "created_at": r["created_at"],
                })
        except Exception as e:
            logger.debug("교차 에이전트 메시지 조회 실패: %s", e)

        conn.close()

        # 시간순 정렬 (최신 먼저)
        messages.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return messages[:limit]
    except Exception:
        return []


# ── SSE 엔드포인트 (B안: 내부통신 실시간 스트림) ──

@router.get("/api/comms/stream")
async def comms_sse_stream():
    """SSE(Server-Sent Events) 실시간 내부통신 스트림.
    프론트엔드에서 EventSource('/api/comms/stream')로 연결.
    새 delegation_log / cross_agent_messages 발생 시 즉시 push.
    """
    queue: asyncio.Queue = asyncio.Queue()
    wm.add_sse_client(queue)

    async def event_generator():
        try:
            # 연결 확인 이벤트
            yield f"event: connected\ndata: {json.dumps({'status':'ok'})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"event: comms\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # keepalive — 30초마다 ping
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            wm.remove_sse_client(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
