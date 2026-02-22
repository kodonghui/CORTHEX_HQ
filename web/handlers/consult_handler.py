"""처장 간 협의(Consult) API.

비유: 회의실 — 에이전트 간 협의 요청을 접수하고 기록하는 곳.
"""
import logging
import time as _time

from fastapi import APIRouter, Request

from ws_manager import wm

logger = logging.getLogger("corthex")

router = APIRouter(tags=["consult"])


@router.post("/api/consult")
async def consult_manager_api(request: Request):
    """처장 간 협의 요청. 에이전트가 다른 에이전트에게 의견/도움을 요청합니다.

    body: {from_agent, to_agent, question, context?}
    반환: {success, id, message}
    """
    try:
        from db import save_delegation_log
        body = await request.json()
        from_agent = body.get("from_agent", "")
        to_agent = body.get("to_agent", "")
        question = body.get("question", "")
        context = body.get("context", "")

        if not from_agent or not to_agent or not question:
            return {"success": False, "error": "from_agent, to_agent, question은 필수입니다."}

        msg_text = f"[협의 요청] {question}"
        if context:
            msg_text += f"\n맥락: {context}"

        row_id = save_delegation_log(
            sender=from_agent,
            receiver=to_agent,
            message=msg_text,
            log_type="consult",
        )

        # WebSocket broadcast
        _log_data = {
            "id": row_id,
            "sender": from_agent,
            "receiver": to_agent,
            "message": msg_text,
            "log_type": "consult",
            "created_at": _time.time(),
        }
        await wm.send_delegation_log(_log_data)

        return {
            "success": True,
            "id": row_id,
            "message": f"{from_agent}가 {to_agent}에게 협의를 요청했습니다.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
