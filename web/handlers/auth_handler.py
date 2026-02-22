"""인증(Auth) API — 로그인·로그아웃·토큰 확인·비밀번호 변경.

비유: 경비실 — 출입 자격을 확인하고 출입증(토큰)을 발급하는 곳.
"""
import time
import uuid as _uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from db import load_setting, save_setting
from state import app_state

router = APIRouter(prefix="/api/auth", tags=["auth"])

_sessions = app_state.sessions  # token → 만료 시간
_SESSION_TTL = 86400 * 7  # 7일


def check_auth(request: Request) -> bool:
    """요청의 인증 상태를 확인합니다."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        token = request.query_params.get("token", "")
    if token and token in _sessions:
        if _sessions[token] > time.time():
            return True
        del _sessions[token]
    return False


@router.get("/status")
async def auth_status(request: Request):
    if check_auth(request):
        return {"bootstrap_mode": False, "role": "ceo", "authenticated": True}
    # 비밀번호가 기본값이고 세션이 없으면 부트스트랩 모드
    stored_pw = load_setting("admin_password")
    if (not stored_pw or stored_pw == "corthex2026") and not _sessions:
        return {"bootstrap_mode": True, "role": "ceo", "authenticated": True}
    return {"bootstrap_mode": False, "role": "viewer", "authenticated": False}


@router.post("/login")
async def login(request: Request):
    """비밀번호 로그인."""
    body = await request.json()
    pw = body.get("password", "")
    stored_pw = load_setting("admin_password") or "corthex2026"
    if pw != stored_pw:
        return JSONResponse({"success": False, "error": "비밀번호가 틀립니다"}, status_code=401)
    token = str(_uuid.uuid4())
    _sessions[token] = time.time() + _SESSION_TTL
    return {"success": True, "token": token, "user": {"role": "ceo", "name": "CEO"}}


@router.post("/logout")
async def logout(request: Request):
    """로그아웃."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token in _sessions:
        del _sessions[token]
    return {"success": True}


@router.get("/check")
async def auth_check(request: Request):
    """토큰 유효성 확인."""
    if check_auth(request):
        return {"authenticated": True, "role": "ceo"}
    return JSONResponse({"authenticated": False}, status_code=401)


@router.post("/change-password")
async def change_password(request: Request):
    """비밀번호 변경."""
    if not check_auth(request):
        return JSONResponse({"success": False, "error": "인증 필요"}, status_code=401)
    body = await request.json()
    current = body.get("current", "")
    new_pw = body.get("new_password", "")
    stored_pw = load_setting("admin_password") or "corthex2026"
    if current != stored_pw:
        return JSONResponse({"success": False, "error": "현재 비밀번호가 틀립니다"}, status_code=401)
    if len(new_pw) < 4:
        return {"success": False, "error": "비밀번호는 4자 이상이어야 합니다"}
    save_setting("admin_password", new_pw)
    return {"success": True}
