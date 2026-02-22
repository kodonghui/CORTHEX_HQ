"""대화(Conversation) API — 대화 메시지 저장·조회·삭제.

비유: 회의록 — CEO와 에이전트 간 대화 기록을 보관하는 곳.
"""
import logging

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from db import (
    save_conversation_message,
    load_conversation_messages,
    clear_conversation_messages,
)

logger = logging.getLogger("corthex")

router = APIRouter(prefix="/api/conversation", tags=["conversation"])


@router.get("")
async def get_conversation():
    """대화 기록을 DB에서 조회합니다."""
    messages = load_conversation_messages(limit=100)
    return messages


@router.post("/save")
async def save_conversation(data: dict = Body(...)):
    """대화 메시지를 DB에 저장합니다.

    요청 본문:
    - type: "user" 또는 "result"
    - user 타입: text 필드 필수
    - result 타입: content, sender_id 등 필드 전달
    """
    try:
        message_type = data.get("type")
        if not message_type:
            return {"success": False, "error": "type 필드가 필요합니다"}

        # type 제외한 나머지 필드들을 kwargs로 전달
        kwargs = {k: v for k, v in data.items() if k != "type"}

        row_id = save_conversation_message(message_type, **kwargs)
        return {"success": True, "id": row_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("")
async def delete_conversation():
    """대화 기록을 모두 삭제합니다."""
    try:
        clear_conversation_messages()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
