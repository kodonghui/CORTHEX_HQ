"""피드백(Feedback) API — 좋아요/싫어요 카운트 관리.

비유: 만족도 조사함 — CEO의 피드백을 집계하는 곳.
"""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from db import save_setting, load_setting

logger = logging.getLogger("corthex")

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


def _load_data(name: str, default=None):
    """DB에서 설정 데이터 로드."""
    db_val = load_setting(name)
    if db_val is not None:
        return db_val
    return default if default is not None else {}


def _save_data(name: str, data) -> None:
    """DB에 설정 데이터 저장."""
    save_setting(name, data)


@router.get("")
async def get_feedback():
    return _load_data("feedback", {"good": 0, "bad": 0, "total": 0})


@router.post("")
async def send_feedback(request: Request):
    """피드백 전송/취소/변경.

    action 파라미터:
      - "send" (기본): 새 피드백 추가 (카운트 +1)
      - "cancel": 기존 피드백 취소 (카운트 -1)
      - "change": 기존 피드백 변경 (이전 카운트 -1 + 새 카운트 +1)
    """
    body = await request.json()
    feedback = _load_data("feedback", {"good": 0, "bad": 0, "total": 0})
    rating = body.get("rating", "")
    action = body.get("action", "send")  # "send", "cancel", "change"
    previous_rating = body.get("previous_rating")  # 변경 시 이전 값

    if not rating:
        return {"success": False, "error": "rating is required"}

    if action == "cancel":
        # 피드백 취소: 해당 카운트 1 감소 (0 이하로 내려가지 않음)
        if rating == "good":
            feedback["good"] = max(0, feedback.get("good", 0) - 1)
        elif rating == "bad":
            feedback["bad"] = max(0, feedback.get("bad", 0) - 1)
    elif action == "change":
        # 피드백 변경: 이전 피드백 카운트 1 감소 + 새 피드백 카운트 1 증가
        if previous_rating == "good":
            feedback["good"] = max(0, feedback.get("good", 0) - 1)
        elif previous_rating == "bad":
            feedback["bad"] = max(0, feedback.get("bad", 0) - 1)
        if rating == "good":
            feedback["good"] = feedback.get("good", 0) + 1
        elif rating == "bad":
            feedback["bad"] = feedback.get("bad", 0) + 1
    else:  # action == "send" (기본값)
        if rating == "good":
            feedback["good"] = feedback.get("good", 0) + 1
        elif rating == "bad":
            feedback["bad"] = feedback.get("bad", 0) + 1

    feedback["total"] = feedback.get("good", 0) + feedback.get("bad", 0)
    _save_data("feedback", feedback)
    return {"success": True, **feedback}


# ── E-1: UI 피드백 모드 ──

@router.get("/ui")
async def get_ui_feedback():
    """UI 피드백 목록 조회."""
    import json
    raw = load_setting("ui_feedback_items", "[]")
    items = json.loads(raw) if isinstance(raw, str) else raw
    return {"success": True, "items": items}


@router.post("/ui")
async def add_ui_feedback(request: Request):
    """UI 피드백 추가 — 클릭 좌표 + 현재 탭 + 코멘트."""
    import json
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))

    body = await request.json()
    raw = load_setting("ui_feedback_items", "[]")
    items = json.loads(raw) if isinstance(raw, str) else raw

    item = {
        "id": int(datetime.now(KST).timestamp() * 1000),
        "x": body.get("x", 0),
        "y": body.get("y", 0),
        "tab": body.get("tab", ""),
        "viewMode": body.get("viewMode", ""),
        "comment": body.get("comment", ""),
        "url": body.get("url", ""),
        "date": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
    }
    items.append(item)
    _save_data("ui_feedback_items", json.dumps(items, ensure_ascii=False))
    logger.info(f"[UI피드백] {item['tab']}/{item['viewMode']} ({item['x']},{item['y']}): {item['comment']}")
    return {"success": True, "item": item, "total": len(items)}


@router.delete("/ui/{item_id}")
async def delete_ui_feedback(item_id: int):
    """UI 피드백 삭제."""
    import json
    raw = load_setting("ui_feedback_items", "[]")
    items = json.loads(raw) if isinstance(raw, str) else raw
    items = [i for i in items if i.get("id") != item_id]
    _save_data("ui_feedback_items", json.dumps(items, ensure_ascii=False))
    return {"success": True}
