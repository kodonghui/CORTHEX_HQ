"""헬스체크(Health) API — 서버 상태 확인.

비유: 건강검진실 — 서버가 살아있는지, 주요 서비스가 동작 중인지 확인.
"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter

from state import app_state

KST = timezone(timedelta(hours=9))

router = APIRouter(tags=["health"])


def _get_agent_count() -> int:
    """에이전트 수를 반환. mini_server.py의 AGENTS 목록 길이를 동적으로 가져옴."""
    try:
        # mini_server 모듈에서 AGENTS를 동적 import (순환 참조 방지)
        import sys
        mini = sys.modules.get("mini_server")
        if mini and hasattr(mini, "AGENTS"):
            return len(mini.AGENTS)
    except Exception:
        pass
    return 0


def _is_telegram_available() -> bool:
    """텔레그램 봇 사용 가능 여부."""
    try:
        import sys
        mini = sys.modules.get("mini_server")
        if mini and hasattr(mini, "_telegram_available"):
            return mini._telegram_available
    except Exception:
        pass
    return False


@router.get("/api/health")
async def health_check():
    """서버 상태 확인."""
    return {
        "status": "ok",
        "mode": "ARM 서버",
        "agents": _get_agent_count(),
        "telegram": _is_telegram_available() and app_state.telegram_app is not None,
        "timestamp": datetime.now(KST).isoformat(),
    }
