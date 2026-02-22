"""Google Calendar OAuth API — 인증 설정, 콜백, 상태 확인.

비유: 캘린더 연동실 — Google Calendar와 OAuth 인증을 연결하고 관리하는 곳.
"""
import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from db import load_setting, save_setting

logger = logging.getLogger("corthex")

router = APIRouter(tags=["calendar"])

_GCAL_SCOPES = ["https://www.googleapis.com/auth/calendar"]


@router.get("/api/google-calendar/setup")
async def google_calendar_setup(request: Request):
    """CEO가 이 링크를 한 번 클릭하면 Google 로그인 화면으로 이동합니다."""
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    redirect_uri = os.getenv("GOOGLE_CALENDAR_REDIRECT_URI", "")
    if not client_id or not redirect_uri:
        return {"error": "GOOGLE_CLIENT_ID 또는 GOOGLE_CALENDAR_REDIRECT_URI가 설정되지 않았습니다."}

    from urllib.parse import urlencode
    params = urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(_GCAL_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    })
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
    return RedirectResponse(url=auth_url)


@router.get("/api/google-calendar/callback")
async def google_calendar_callback(request: Request, code: str = ""):
    """Google이 인증 코드를 보내면 토큰으로 교환하여 DB에 저장합니다."""
    if not code:
        return HTMLResponse("<h2>인증 코드가 없습니다. 다시 시도해주세요.</h2>")

    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    redirect_uri = os.getenv("GOOGLE_CALENDAR_REDIRECT_URI", "")

    if not client_id or not client_secret:
        return HTMLResponse("<h2>GOOGLE_CLIENT_ID/SECRET이 설정되지 않았습니다.</h2>")

    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if resp.status_code != 200:
                return HTMLResponse(f"<h2>토큰 교환 실패: {resp.text}</h2>")
            token_data = resp.json()
    except Exception as e:
        return HTMLResponse(f"<h2>토큰 교환 오류: {e}</h2>")

    # DB에 저장
    creds_info = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": token_data.get("refresh_token", ""),
        "token": token_data.get("access_token", ""),
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": _GCAL_SCOPES,
    }
    save_setting("google_calendar_credentials", creds_info)
    logger.info("[GCAL] Google Calendar OAuth 토큰 저장 완료")
    return HTMLResponse(
        "<h2>Google Calendar 연동 완료!</h2>"
        "<p>이제 캘린더 도구가 정상 작동합니다. 이 창을 닫으셔도 됩니다.</p>"
    )


@router.get("/api/google-calendar/status")
async def google_calendar_status():
    """Google Calendar 연동 상태를 확인합니다."""
    creds = load_setting("google_calendar_credentials")
    if creds and creds.get("refresh_token"):
        return {"connected": True, "message": "Google Calendar 연동됨"}
    return {"connected": False, "message": "연동 필요 — /api/google-calendar/setup 방문"}
