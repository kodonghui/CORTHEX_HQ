"""대화(Conversation) API — 멀티턴 대화 세션 관리 + 메시지 저장·조회·삭제.

비유: 회의록 관리 시스템 — 여러 회의를 세션별로 보관하고, 이전 회의 내용을 참조할 수 있음.
"""
import logging

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse

from handlers.auth_handler import get_auth_org
from db import (
    save_conversation_message,
    load_conversation_messages,
    clear_conversation_messages,
    create_conversation,
    list_conversations,
    get_conversation,
    update_conversation,
    load_conversation_messages_by_id,
    delete_conversation,
)

logger = logging.getLogger("corthex")

router = APIRouter(prefix="/api/conversation", tags=["conversation"])


# ── Session Management (멀티턴 대화 세션) ──

@router.post("/sessions")
async def create_session(data: dict = Body(...)):
    """새 대화 세션을 생성합니다."""
    title = data.get("title", "새 대화")
    agent_id = data.get("agent_id") or None
    org = data.get("org", "")
    session = create_conversation(agent_id=agent_id, title=title, org=org)
    return {"success": True, "session": session}


@router.get("/sessions")
async def get_sessions(request: Request, limit: int = Query(30), org: str = Query("")):
    """대화 세션 목록을 반환합니다 (최신순). 인증 org 자동 적용."""
    auth_org = get_auth_org(request)
    effective_org = auth_org or org  # 인증 org 우선 (sister→saju 강제)
    sessions = list_conversations(limit=limit, org=effective_org or None)
    return sessions


@router.get("/sessions/{conversation_id}")
async def get_session(conversation_id: str):
    """특정 대화 세션 정보를 반환합니다."""
    session = get_conversation(conversation_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "대화를 찾을 수 없습니다"})
    return session


@router.patch("/sessions/{conversation_id}")
async def patch_session(conversation_id: str, data: dict = Body(...)):
    """대화 세션 메타데이터를 업데이트합니다 (제목, 보관 등)."""
    update_conversation(conversation_id, **data)
    return {"success": True}


@router.delete("/sessions/{conversation_id}")
async def delete_session(conversation_id: str):
    """대화 세션과 관련 메시지를 삭제합니다."""
    delete_conversation(conversation_id)
    return {"success": True}


@router.get("/sessions/{conversation_id}/messages")
async def get_session_messages(conversation_id: str, limit: int = Query(200)):
    """특정 대화 세션의 메시지를 조회합니다."""
    messages = load_conversation_messages_by_id(conversation_id, limit=limit)
    return messages


# ── Legacy endpoints (하위 호환) ──

@router.get("")
async def get_conversation_legacy():
    """[레거시] 대화 기록을 DB에서 조회합니다."""
    messages = load_conversation_messages(limit=100)
    return messages


@router.post("/save")
async def save_conversation_endpoint(data: dict = Body(...)):
    """대화 메시지를 DB에 저장합니다 (conversation_id 지원)."""
    try:
        message_type = data.get("type")
        if not message_type:
            return {"success": False, "error": "type 필드가 필요합니다"}

        kwargs = {k: v for k, v in data.items() if k != "type"}

        row_id = save_conversation_message(message_type, **kwargs)

        # user 메시지이고 conversation_id가 있으면 turn_count 증가
        conv_id = data.get("conversation_id")
        if message_type == "user" and conv_id:
            try:
                conv = get_conversation(conv_id)
                if conv:
                    update_conversation(conv_id, turn_count=conv["turn_count"] + 1)
            except Exception:
                pass

        return {"success": True, "id": row_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("")
async def delete_conversation_legacy():
    """[레거시] 대화 기록을 모두 삭제합니다."""
    try:
        clear_conversation_messages()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
