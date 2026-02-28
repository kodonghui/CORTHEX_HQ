"""SNS 관련 API — 플랫폼 연결, OAuth, 게시 대기열, 발행, 쿠키 관리.

비유: 홍보실 — SNS 플랫폼 연동, 콘텐츠 승인/발행을 담당하는 곳.
"""
import asyncio
import logging
import os
import pickle
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from db import save_setting, load_setting, create_task, update_task

logger = logging.getLogger("corthex")

router = APIRouter(tags=["sns"])

# ── SNS 플랫폼 목록 + 환경변수 매핑 ──
_SNS_PLATFORMS = ["instagram", "youtube", "tistory", "naver_blog", "naver_cafe", "daum_cafe"]

_SNS_ENV_MAP = {
    "instagram": "INSTAGRAM_ACCESS_TOKEN",
    "youtube": "GOOGLE_CLIENT_ID",
    "tistory": "KAKAO_ID",
    "naver_blog": "NAVER_ID",
    "naver_cafe": "NAVER_CLIENT_ID",
    "daum_cafe": "DAUM_ID",
}


# ── 플랫폼 연결 상태 ──

@router.get("/api/sns/status")
async def get_sns_status():
    """SNS 플랫폼 연결 상태 — 환경변수 + OAuth 토큰 만료 정보."""
    result = {}
    for p in _SNS_PLATFORMS:
        env_key = _SNS_ENV_MAP.get(p, "")
        has_key = bool(os.getenv(env_key, ""))
        info = {
            "connected": has_key,
            "username": os.getenv(f"{p.upper()}_USERNAME", ""),
            "env_key": env_key,  # D-3: 어떤 환경변수가 필요한지 표시
        }
        # D-3: OAuth 토큰 만료 시간 확인
        try:
            from oauth_manager import OAuthManager
            oauth = OAuthManager()
            token = oauth.get_token(p)
            if token:
                info["token_valid"] = not token.is_expired
                info["token_expires_at"] = token.expires_at if hasattr(token, "expires_at") else None
            else:
                info["token_valid"] = None  # 토큰 없음
        except Exception:
            info["token_valid"] = None
        result[p] = info
    return result


@router.get("/api/sns/oauth/status")
async def get_sns_oauth_status():
    """SNS OAuth 인증 상태."""
    result = {}
    for p in _SNS_PLATFORMS:
        env_key = _SNS_ENV_MAP.get(p, "")
        has_key = bool(os.getenv(env_key, ""))
        info = {"authenticated": has_key, "env_key": env_key}
        try:
            from oauth_manager import OAuthManager
            oauth = OAuthManager()
            info["has_token"] = oauth.has_valid_token(p)
        except Exception:
            info["has_token"] = False
        result[p] = info
    return result


# ── OAuth 인증 ──

@router.get("/api/sns/auth/{platform}")
async def sns_auth(platform: str):
    """플랫폼별 OAuth 인증 URL을 반환합니다."""
    try:
        from src.tools.sns.oauth_manager import OAuthManager
        oauth = OAuthManager()
        url = oauth.get_auth_url(platform)
        if url:
            return {"success": True, "url": url, "platform": platform}
        else:
            return {"success": False, "error": f"{platform} OAuth 설정이 없습니다."}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/sns/oauth/callback/{platform}")
async def sns_oauth_callback(platform: str, code: str = "", state: str = "", request: Request = None):
    """OAuth 인증 코드를 받아서 토큰으로 교환 후 저장합니다."""
    if not code:
        return HTMLResponse(f"""
            <html><body style="font-family:sans-serif;text-align:center;padding:50px">
            <h2>&#10060; {platform} 인증 실패</h2>
            <p>인증 코드가 전달되지 않았습니다.</p>
            </body></html>
        """)
    try:
        from src.tools.sns.oauth_manager import OAuthManager
        oauth = OAuthManager()
        token = await oauth.exchange_code(platform, code)
        if token:
            return HTMLResponse(f"""
                <html><body style="font-family:sans-serif;text-align:center;padding:50px">
                <h2>&#9989; {platform} 인증 완료!</h2>
                <p>이 창을 닫으셔도 됩니다.</p>
                <script>setTimeout(()=>window.close(),3000)</script>
                </body></html>
            """)
        else:
            return HTMLResponse(f"""
                <html><body style="font-family:sans-serif;text-align:center;padding:50px">
                <h2>&#10060; {platform} 인증 실패</h2>
                <p>토큰 교환에 실패했습니다.</p>
                </body></html>
            """)
    except Exception as e:
        return HTMLResponse(f"""
            <html><body style="font-family:sans-serif;text-align:center;padding:50px">
            <h2>&#10060; 오류 발생</h2>
            <p>{str(e)}</p>
            </body></html>
        """)


# ── 인스타그램 ──

@router.post("/api/sns/instagram/photo")
async def post_instagram_photo(request: Request):
    return {"success": False, "error": "인스타그램 API가 아직 연동되지 않았습니다."}


@router.post("/api/sns/instagram/reel")
async def post_instagram_reel(request: Request):
    return {"success": False, "error": "인스타그램 API가 아직 연동되지 않았습니다."}


@router.get("/api/debug/instagram-token")
async def debug_instagram_token():
    """인스타그램 토큰 상태 디버깅 — 토큰 유효성 + 계정 정보 확인."""
    import httpx as _httpx

    result = {
        "env_token_exists": bool(os.getenv("INSTAGRAM_ACCESS_TOKEN", "")),
        "env_user_id_exists": bool(os.getenv("INSTAGRAM_USER_ID", "")),
        "env_app_id_exists": bool(os.getenv("INSTAGRAM_APP_ID", "")),
        "env_app_secret_exists": bool(os.getenv("INSTAGRAM_APP_SECRET", "")),
        "token_prefix": (os.getenv("INSTAGRAM_ACCESS_TOKEN", "")[:20] + "...") if os.getenv("INSTAGRAM_ACCESS_TOKEN") else None,
        "user_id": os.getenv("INSTAGRAM_USER_ID", ""),
    }

    # DB에 저장된 OAuth 토큰 확인
    try:
        from src.tools.sns.oauth_manager import OAuthManager
        oauth = OAuthManager()
        db_token = oauth.get_token("instagram")
        if db_token:
            result["db_token_exists"] = True
            result["db_token_expired"] = db_token.is_expired
            result["db_token_expires_at"] = db_token.expires_at
            result["db_has_refresh"] = bool(db_token.refresh_token)
        else:
            result["db_token_exists"] = False
    except Exception as e:
        result["db_error"] = str(e)

    # 실제 Graph API 호출로 토큰 유효성 검증
    access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    if access_token:
        try:
            async with _httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://graph.instagram.com/me",
                    params={"fields": "id,username,account_type,media_count", "access_token": access_token},
                )
                data = resp.json()
                if "error" in data:
                    result["api_valid"] = False
                    result["api_error"] = data["error"].get("message", str(data["error"]))
                    result["api_error_code"] = data["error"].get("code")
                    result["api_error_type"] = data["error"].get("type")
                else:
                    result["api_valid"] = True
                    result["api_username"] = data.get("username", "")
                    result["api_account_type"] = data.get("account_type", "")
                    result["api_media_count"] = data.get("media_count", 0)
        except Exception as e:
            result["api_error"] = f"요청 실패: {str(e)}"
    else:
        result["api_valid"] = False
        result["api_error"] = "INSTAGRAM_ACCESS_TOKEN 환경변수 없음"

    return result


# ── 유튜브 ──

@router.post("/api/sns/youtube/upload")
async def post_youtube_video(request: Request):
    return {"success": False, "error": "유튜브 API가 아직 연동되지 않았습니다."}


# ── 게시 대기열 (Queue) ──

@router.get("/api/sns/queue")
async def get_sns_queue(status: str = ""):
    """SNS 게시 대기열 — SQLite DB에서 직접 로드 (SNSManager와 동일 소스)."""
    queue = load_setting("sns_publish_queue", []) or []
    if status:
        queue = [q for q in queue if q.get("status") == status]
    return {"items": queue, "total": len(queue)}


@router.delete("/api/sns/queue")
async def clear_sns_queue(status: str = ""):
    """SNS 대기열 초기화. status 파라미터 없으면 전체, 있으면 해당 상태만."""
    queue = load_setting("sns_publish_queue", []) or []
    if status:
        remaining = [q for q in queue if q.get("status") != status]
        removed = len(queue) - len(remaining)
        save_setting("sns_publish_queue", remaining)
        return {"success": True, "removed": removed, "remaining": len(remaining)}
    else:
        save_setting("sns_publish_queue", [])
        return {"success": True, "removed": len(queue), "remaining": 0}


@router.delete("/api/sns/queue/{item_id}")
async def delete_sns_item(item_id: str):
    """SNS 대기열에서 특정 항목 삭제."""
    queue = load_setting("sns_publish_queue", []) or []
    new_queue = [q for q in queue if q.get("request_id") != item_id]
    if len(new_queue) == len(queue):
        return {"success": False, "error": f"요청 ID를 찾을 수 없음: {item_id}"}
    save_setting("sns_publish_queue", new_queue)
    return {"success": True, "removed": 1, "remaining": len(new_queue)}


# ── 승인 / 거절 / 재제출 / 발행 ──

@router.post("/api/sns/approve/{item_id}")
async def approve_sns(item_id: str):
    """CEO가 SNS 발행 요청을 승인 → 자동 발행까지 진행."""
    queue = load_setting("sns_publish_queue", []) or []
    for item in queue:
        if item.get("request_id") == item_id:
            if item.get("status") != "pending":
                return {"success": False, "error": f"이미 처리됨: {item.get('status')}"}
            item["status"] = "approved"
            item["approved_at"] = time.time()
            save_setting("sns_publish_queue", queue)
            # 자동 발행 (백그라운드 — Selenium 느리므로 즉시 응답)
            asyncio.create_task(_auto_publish_after_approve(item_id))
            return {
                "success": True,
                "status": "approved",
                "request_id": item_id,
                "auto_publish": True,
                "message": "승인 완료. 자동 발행 진행중...",
            }
    return {"success": False, "error": f"요청 ID를 찾을 수 없음: {item_id}"}


async def _auto_publish_after_approve(item_id: str):
    """승인 직후 자동 발행 (백그라운드 태스크).

    publish_sns()와 동일한 로직이지만, 실패해도 approved 상태 유지.
    """
    try:
        queue = load_setting("sns_publish_queue", []) or []
        target = None
        for item in queue:
            if item.get("request_id") == item_id:
                target = item
                break
        if not target or target.get("status") != "approved":
            logger.warning("[SNS] 자동 발행 스킵: %s (상태: %s)", item_id, target.get("status") if target else "없음")
            return

        from src.tools.sns.base_publisher import PostContent
        from src.tools.sns.oauth_manager import OAuthManager
        oauth = OAuthManager()
        platform = target.get("platform", "")
        content_data = target.get("content", {})

        publisher = _get_publisher(platform, oauth)
        if not publisher:
            target["status"] = "failed"
            target["result"] = {"success": False, "message": f"퍼블리셔 없음: {platform}"}
            save_setting("sns_publish_queue", queue)
            logger.error("[SNS] 자동 발행 실패 — 퍼블리셔 없음: %s", platform)
            return

        content = PostContent(**content_data)
        result = await publisher.publish(content)
        target["status"] = "published" if result.success else "failed"
        target["published_at"] = time.time()
        target["result"] = {
            "success": result.success,
            "post_id": result.post_id,
            "post_url": result.post_url,
            "message": result.message,
        }
        save_setting("sns_publish_queue", queue)
        logger.info("[SNS] 자동 발행 %s: %s → %s", "성공" if result.success else "실패", item_id, platform)

    except Exception as e:
        logger.error("[SNS] 자동 발행 오류: %s — %s", item_id, e, exc_info=True)
        try:
            queue = load_setting("sns_publish_queue", []) or []
            for item in queue:
                if item.get("request_id") == item_id:
                    item["status"] = "failed"
                    item["result"] = {"success": False, "message": str(e)}
                    save_setting("sns_publish_queue", queue)
                    break
        except Exception:
            pass


def _get_publisher(platform: str, oauth):
    """플랫폼별 퍼블리셔 인스턴스 반환."""
    try:
        if platform == "tistory":
            from src.tools.sns.tistory_publisher import TistoryPublisher
            return TistoryPublisher(oauth)
        elif platform == "instagram":
            from src.tools.sns.instagram_publisher import InstagramPublisher
            return InstagramPublisher(oauth)
        elif platform == "daum_cafe":
            from src.tools.sns.daum_cafe_publisher import DaumCafePublisher
            return DaumCafePublisher(oauth)
        elif platform == "youtube":
            from src.tools.sns.youtube_publisher import YouTubePublisher
            return YouTubePublisher(oauth)
        elif platform == "naver_blog":
            from src.tools.sns.naver_blog_publisher import NaverBlogPublisher
            return NaverBlogPublisher(oauth)
        elif platform == "naver_cafe":
            from src.tools.sns.naver_cafe_publisher import NaverCafePublisher
            return NaverCafePublisher(oauth)
    except ImportError as e:
        logger.error("[SNS] 퍼블리셔 import 실패: %s — %s", platform, e)
    return None


@router.post("/api/sns/reject/{item_id}")
async def reject_sns(item_id: str, request: Request):
    """CEO가 SNS 발행 요청을 거절 -> 자동으로 원본 전문가에게 재작업 위임."""
    body = {}
    try:
        body = await request.json()
    except Exception as e:
        logger.debug("SNS 거절 요청 바디 파싱 실패: %s", e)
    reason = body.get("reason", "")
    queue = load_setting("sns_publish_queue", []) or []
    for item in queue:
        if item.get("request_id") == item_id:
            # 상태를 rework로 변경 (rejected가 아닌 재작업 요청)
            item["status"] = "rework"
            item["result"] = {"reason": reason}
            item["rework_requested_at"] = time.time()
            item.setdefault("revision", 0)
            item["revision"] += 1
            save_setting("sns_publish_queue", queue)

            # 백그라운드에서 원본 전문가에게 재작업 위임
            asyncio.create_task(_rework_delegate(item, reason))

            return {"success": True, "status": "rework", "request_id": item_id}
    return {"success": False, "error": f"요청 ID를 찾을 수 없음: {item_id}"}


async def _rework_delegate(item: dict, reason: str):
    """거절된 콘텐츠를 원본 전문가에게 재작업 위임.

    _process_ai_command는 arm_server.py에 정의되어 있으므로 런타임에 참조.
    """
    try:
        requested_by = item.get("requested_by", "content_specialist")
        platform = item.get("platform", "")
        content = item.get("content", {})
        title = content.get("title", "제목 없음")
        body_text = content.get("body", "")[:500]
        request_id = item.get("request_id", "")
        revision = item.get("revision", 1)

        rework_command = (
            f"[재작업 요청 #{revision}] CEO가 '{platform}' 콘텐츠를 수정 요청했습니다.\n\n"
            f"## 거절 사유\n{reason}\n\n"
            f"## 원본 콘텐츠\n- 제목: {title}\n- 본문 (앞부분): {body_text}...\n\n"
            f"## 지시사항\n"
            f"위 거절 사유를 반영하여 콘텐츠를 수정한 후, "
            f"sns_manager 도구(action=submit)로 다시 제출하세요.\n"
            f"request_id: {request_id}"
        )

        task = create_task(
            command=rework_command,
            agent_id=requested_by,
            source="rework",
        )
        update_task(task["task_id"], status="running")

        # _process_ai_command는 arm_server.py 내부 함수 — 런타임 import
        import arm_server as _ms
        result = await _ms._process_ai_command(
            rework_command,
            task["task_id"],
            target_agent_id=requested_by,
        )

        if "error" in result:
            update_task(task["task_id"], status="failed",
                        result_summary=f"재작업 위임 실패: {result.get('error', '')[:200]}",
                        success=0)
            logger.error("[REWORK] 재작업 위임 실패: %s", result.get("error"))
        else:
            update_task(task["task_id"], status="completed",
                        result_summary=f"재작업 완료 (revision #{revision})",
                        success=1,
                        time_seconds=result.get("time_seconds", 0))
            logger.info("[REWORK] 재작업 완료: %s → %s", request_id, requested_by)

    except Exception as e:
        logger.error("[REWORK] 재작업 위임 오류: %s", e, exc_info=True)


@router.post("/api/sns/resubmit/{item_id}")
async def resubmit_sns(item_id: str, request: Request):
    """재작업 완료 후 콘텐츠 재제출 -> 승인큐 재등록."""
    body = {}
    try:
        body = await request.json()
    except Exception as e:
        logger.debug("SNS 재제출 요청 바디 파싱 실패: %s", e)
    queue = load_setting("sns_publish_queue", []) or []
    for item in queue:
        if item.get("request_id") == item_id:
            if item.get("status") not in ("rework", "rejected"):
                return {"success": False, "error": f"재제출 불가 상태: {item.get('status')}"}
            # 새 콘텐츠가 있으면 업데이트
            new_content = body.get("content")
            if new_content:
                item["content"] = new_content
            item["status"] = "pending"
            item["resubmitted_at"] = time.time()
            save_setting("sns_publish_queue", queue)
            return {"success": True, "status": "pending", "request_id": item_id}
    return {"success": False, "error": f"요청 ID를 찾을 수 없음: {item_id}"}


@router.post("/api/sns/publish/{item_id}")
async def publish_sns(item_id: str):
    """승인된 SNS 요청을 실제 발행 (서버에서 SNSManager 경유)."""
    queue = load_setting("sns_publish_queue", []) or []
    target = None
    for item in queue:
        if item.get("request_id") == item_id:
            target = item
            break
    if not target:
        return {"success": False, "error": f"요청 ID를 찾을 수 없음: {item_id}"}
    if target.get("status") != "approved":
        return {"success": False, "error": f"승인되지 않은 요청: {target.get('status')}"}
    # SNSManager를 통한 실제 발행
    try:
        from src.tools.sns.base_publisher import PostContent
        from src.tools.sns.oauth_manager import OAuthManager
        oauth = OAuthManager()
        platform = target.get("platform", "")
        content_data = target.get("content", {})
        publisher = _get_publisher(platform, oauth)
        if not publisher:
            return {"success": False, "error": f"퍼블리셔 없음: {platform}"}
        content = PostContent(**content_data)
        result = await publisher.publish(content)
        target["status"] = "published" if result.success else "failed"
        target["published_at"] = time.time()
        target["result"] = {
            "success": result.success,
            "post_id": result.post_id,
            "post_url": result.post_url,
            "message": result.message,
        }
        save_setting("sns_publish_queue", queue)
        return {"success": result.success, "status": target["status"], "result": target["result"]}
    except Exception as e:
        logger.error("[SNS] 발행 실패: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


# ── 이벤트 로그 ──

@router.get("/api/sns/events")
async def get_sns_events(limit: int = 50):
    """SNS 이벤트 로그 — 발행 완료/실패된 항목."""
    queue = load_setting("sns_publish_queue", []) or []
    events = [q for q in queue if q.get("status") in ("published", "failed", "rejected", "rework")]
    events.sort(key=lambda x: x.get("published_at") or x.get("created_at", 0), reverse=True)
    return {"items": events[:limit], "total": len(events)}


# ── 쿠키 관리 API ──
# Selenium 퍼블리셔(네이버/카카오)의 CAPTCHA 우회용.
# 대표님 PC 브라우저에서 Cookie-Editor로 쿠키 추출 → 서버에 업로드 → Selenium이 쿠키로 로그인.

_COOKIE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "sns_cookies"
_VALID_COOKIE_PLATFORMS = {"naver", "kakao"}
_KST = timezone(timedelta(hours=9))
_PLATFORM_EXPIRY_DAYS = {"naver": 90, "kakao": 30}


@router.post("/api/sns/cookies/{platform}")
async def upload_sns_cookies(platform: str, request: Request):
    """Cookie-Editor에서 추출한 쿠키 JSON을 서버에 저장 (pickle)."""
    if platform not in _VALID_COOKIE_PLATFORMS:
        return JSONResponse({"success": False, "error": f"지원 플랫폼: {sorted(_VALID_COOKIE_PLATFORMS)}"}, 400)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "JSON 파싱 실패"}, 400)

    # Cookie-Editor JSON 배열 또는 document.cookie 문자열 둘 다 지원
    if isinstance(body, str):
        domain = ".naver.com" if platform == "naver" else ".kakao.com"
        cookies = [
            {"name": p.split("=", 1)[0].strip(), "value": p.split("=", 1)[1].strip(),
             "domain": domain, "path": "/", "secure": True, "httpOnly": False}
            for p in body.split(";") if "=" in p
        ]
    elif isinstance(body, list):
        cookies = body
    else:
        return JSONResponse({"success": False, "error": "JSON 배열 또는 문자열 필요"}, 400)

    if not cookies:
        return JSONResponse({"success": False, "error": "쿠키가 비어있습니다"}, 400)

    # 구조 검증 + 정규화
    normalized = []
    for c in cookies:
        if not isinstance(c, dict) or "name" not in c or "value" not in c:
            continue
        normalized.append({
            "name": c["name"], "value": c["value"],
            "domain": c.get("domain", f".{platform}.com"),
            "path": c.get("path", "/"),
            "secure": c.get("secure", True),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": c.get("sameSite", "None"),
        })

    if not normalized:
        return JSONResponse({"success": False, "error": "유효한 쿠키가 없습니다 (name/value 필요)"}, 400)

    # pickle 저장
    _COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_COOKIE_DIR / f"{platform}_cookies.pkl", "wb") as f:
        pickle.dump(normalized, f)

    now_kst = datetime.now(_KST).isoformat()
    save_setting(f"sns_cookie_{platform}_uploaded_at", now_kst)

    logger.info("[SNS Cookie] %s 쿠키 %d개 업로드 완료", platform, len(normalized))
    return {"success": True, "platform": platform, "cookie_count": len(normalized), "uploaded_at": now_kst}


@router.get("/api/sns/cookies/status")
async def get_sns_cookies_status():
    """각 플랫폼의 쿠키 등록 상태 조회 (쿠키 값은 반환하지 않음)."""
    result = {}
    for platform in _VALID_COOKIE_PLATFORMS:
        pkl = _COOKIE_DIR / f"{platform}_cookies.pkl"
        if pkl.exists():
            uploaded_at = load_setting(f"sns_cookie_{platform}_uploaded_at")
            try:
                with open(pkl, "rb") as f:
                    cookie_count = len(pickle.load(f))
            except Exception:
                cookie_count = 0
            age_days = round((time.time() - pkl.stat().st_mtime) / 86400, 1)
            expiry_days = _PLATFORM_EXPIRY_DAYS.get(platform, 90)
            estimated_expiry = None
            if uploaded_at:
                try:
                    estimated_expiry = (datetime.fromisoformat(uploaded_at) + timedelta(days=expiry_days)).strftime("%Y-%m-%d")
                except Exception:
                    pass
            result[platform] = {
                "exists": True, "uploaded_at": uploaded_at,
                "file_age_days": age_days, "cookie_count": cookie_count,
                "estimated_expiry": estimated_expiry,
                "expiry_warning": age_days > (expiry_days * 0.8),
            }
        else:
            result[platform] = {"exists": False, "uploaded_at": None, "file_age_days": None,
                                "cookie_count": 0, "estimated_expiry": None, "expiry_warning": False}
    return result


@router.delete("/api/sns/cookies/{platform}")
async def delete_sns_cookies(platform: str):
    """특정 플랫폼의 쿠키 파일 삭제."""
    if platform not in _VALID_COOKIE_PLATFORMS:
        return JSONResponse({"success": False, "error": f"지원 플랫폼: {sorted(_VALID_COOKIE_PLATFORMS)}"}, 400)
    pkl = _COOKIE_DIR / f"{platform}_cookies.pkl"
    if pkl.exists():
        pkl.unlink()
    save_setting(f"sns_cookie_{platform}_uploaded_at", None)
    logger.info("[SNS Cookie] %s 쿠키 삭제 완료", platform)
    return {"success": True, "platform": platform}
