"""텔레그램 봇 상태 진단 API.

비유: 통신실 — 텔레그램 봇의 연결 상태를 확인하고 테스트 메시지를 보내는 곳.
"""
import logging
import os
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter

from state import app_state

logger = logging.getLogger("corthex")

router = APIRouter(tags=["telegram"])

KST = timezone(timedelta(hours=9))


@router.get("/api/telegram-status")
async def telegram_status():
    """텔레그램 봇 진단 정보 반환."""
    _diag = app_state.diag
    try:
        _telegram_available = bool(
            __import__("importlib").util.find_spec("telegram")
        )
    except Exception:
        _telegram_available = False

    polling_running = False
    if (app_state.telegram_app
            and hasattr(app_state.telegram_app, "updater")
            and app_state.telegram_app.updater):
        polling_running = app_state.telegram_app.updater.running

    return {
        **_diag,
        "tg_app_exists": app_state.telegram_app is not None,
        "tg_available": _telegram_available,
        "tg_polling_running": polling_running,
        "env_token_set": bool(os.getenv("TELEGRAM_BOT_TOKEN", "")),
        "env_ceo_id": os.getenv("TELEGRAM_CEO_CHAT_ID", ""),
    }


@router.post("/api/debug/telegram-test")
async def telegram_test():
    """텔레그램 봇 테스트 — CEO에게 테스트 메시지 전송."""
    _diag = app_state.diag
    if not app_state.telegram_app:
        return {"ok": False, "error": "봇 미시작 (tg_app=None)", "diag": _diag}
    ceo_id = os.getenv("TELEGRAM_CEO_CHAT_ID", "")
    if not ceo_id:
        return {"ok": False, "error": "TELEGRAM_CEO_CHAT_ID 미설정"}
    try:
        now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        msg = await app_state.telegram_app.bot.send_message(
            chat_id=int(ceo_id),
            text=f"CORTHEX HQ 텔레그램 봇 테스트\n시간: {now} KST\n상태: 정상",
        )
        return {"ok": True, "message_id": msg.message_id, "chat_id": ceo_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}
