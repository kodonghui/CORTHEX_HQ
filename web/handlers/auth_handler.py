"""인증(Auth) API — 로그인·로그아웃·토큰 확인·비밀번호 변경.

비유: 경비실 — 출입 자격을 확인하고 출입증(토큰)을 발급하는 곳.
역할 기반: CEO(대표님) / sister(누나) — 역할별 비밀번호 분리.
"""
import time
import uuid as _uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from db import load_setting, save_setting
from state import app_state

router = APIRouter(prefix="/api/auth", tags=["auth"])

# token → {"expiry": float, "role": str}
_sessions: dict = app_state.sessions
_SESSION_TTL = 86400 * 7  # 7일


def _get_session(token: str) -> dict | None:
    """토큰에 해당하는 유효한 세션을 반환. 만료 시 삭제 후 None."""
    if not token or token not in _sessions:
        return None
    s = _sessions[token]
    # 구버전 호환: float 형태(이전 세션) → dict로 취급
    expiry = s["expiry"] if isinstance(s, dict) else s
    if expiry > time.time():
        return s if isinstance(s, dict) else {"expiry": s, "role": "ceo"}
    del _sessions[token]
    return None


def _extract_token(request: Request) -> str:
    """요청에서 토큰 추출: Authorization 헤더 → query param → 쿠키 순."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        token = request.query_params.get("token", "")
    if not token:
        token = request.cookies.get("corthex_token", "")
    return token


def check_auth(request: Request) -> bool:
    """요청의 인증 상태를 확인합니다."""
    return _get_session(_extract_token(request)) is not None


def get_auth_role(request: Request) -> str:
    """인증된 사용자의 역할 반환. 미인증 시 'viewer'."""
    s = _get_session(_extract_token(request))
    return s.get("role", "ceo") if s else "viewer"


def get_auth_org(request: Request) -> str:
    """인증된 사용자의 org 반환. sister→'saju', ceo→'', 미인증→''."""
    s = _get_session(_extract_token(request))
    return s.get("org", "") if s else ""


@router.get("/status")
async def auth_status(request: Request):
    token = _extract_token(request)
    s = _get_session(token)
    if s:
        return {"bootstrap_mode": False, "role": s.get("role", "ceo"), "org": s.get("org", ""), "authenticated": True}
    # 비밀번호가 기본값이고 세션이 없으면 부트스트랩 모드
    stored_pw = load_setting("admin_password")
    if (not stored_pw or stored_pw == "corthex2026") and not _sessions:
        return {"bootstrap_mode": True, "role": "ceo", "org": "", "authenticated": True}
    return {"bootstrap_mode": False, "role": "viewer", "org": "", "authenticated": False}


@router.post("/login")
async def login(request: Request):
    """역할 기반 비밀번호 로그인. role: 'ceo' | 'sister'"""
    body = await request.json()
    pw = body.get("password", "")
    role = body.get("role", "ceo")  # 'ceo' or 'sister'

    if role == "sister":
        stored_pw = load_setting("sister_password") or "sister2026"
        user_name = "누나"
    else:
        role = "ceo"
        stored_pw = load_setting("admin_password") or "corthex2026"
        user_name = "CEO"

    if pw != stored_pw:
        return JSONResponse({"success": False, "error": "비밀번호가 틀립니다"}, status_code=401)

    token = str(_uuid.uuid4())
    org = "saju" if role == "sister" else ""
    _sessions[token] = {"expiry": time.time() + _SESSION_TTL, "role": role, "org": org}
    return {"success": True, "token": token, "user": {"role": role, "name": user_name, "org": org}}


@router.post("/logout")
async def logout(request: Request):
    """로그아웃."""
    token = _extract_token(request)
    if token in _sessions:
        del _sessions[token]
    return {"success": True}


@router.get("/check")
async def auth_check(request: Request):
    """토큰 유효성 확인."""
    s = _get_session(_extract_token(request))
    if s:
        return {"authenticated": True, "role": s.get("role", "ceo"), "org": s.get("org", "")}
    return JSONResponse({"authenticated": False}, status_code=401)


@router.post("/change-password")
async def change_password(request: Request):
    """비밀번호 변경 (CEO용 / 누나용 분리)."""
    if not check_auth(request):
        return JSONResponse({"success": False, "error": "인증 필요"}, status_code=401)
    body = await request.json()
    current = body.get("current", "")
    new_pw = body.get("new_password", "")
    target_role = body.get("role", "ceo")  # 어떤 역할 비밀번호를 변경할지

    if target_role == "sister":
        stored_pw = load_setting("sister_password") or "sister2026"
        setting_key = "sister_password"
    else:
        stored_pw = load_setting("admin_password") or "corthex2026"
        setting_key = "admin_password"

    if current != stored_pw:
        return JSONResponse({"success": False, "error": "현재 비밀번호가 틀립니다"}, status_code=401)
    if len(new_pw) < 4:
        return {"success": False, "error": "비밀번호는 4자 이상이어야 합니다"}
    save_setting(setting_key, new_pw)
    return {"success": True}
