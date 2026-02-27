"""
SNS Manager - 통합 SNS 퍼블리싱 도구.

CORTHEX HQ의 ToolPool에 등록되는 메인 SNS 도구입니다.
- 콘텐츠 Specialist가 작성 → CMO가 검토 → CEO 승인 → CMO가 퍼블리싱
- CEO 승인 대기 큐 (pending_queue)
- 승인된 게시물만 CMO 이상 직급이 실제 퍼블리싱 실행
- 전체 플랫폼 상태 조회
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, TYPE_CHECKING

from src.tools.base import BaseTool
from src.tools.sns.base_publisher import PostContent, PublishResult
from src.tools.sns.oauth_manager import OAuthManager

try:
    from src.tools.sns.tistory_publisher import TistoryPublisher
    _TISTORY_AVAILABLE = True
except ImportError:
    TistoryPublisher = None
    _TISTORY_AVAILABLE = False

try:
    from src.tools.sns.youtube_publisher import YouTubePublisher
    _YOUTUBE_AVAILABLE = True
except ImportError:
    YouTubePublisher = None
    _YOUTUBE_AVAILABLE = False

# Instagram — 비즈니스 계정 전환 전까지 잠금
# try:
#     from src.tools.sns.instagram_publisher import InstagramPublisher
#     _INSTAGRAM_AVAILABLE = True
# except ImportError:
InstagramPublisher = None
_INSTAGRAM_AVAILABLE = False

# 네이버카페 — 대표님 사용 안 함 (삭제)
# try:
#     from src.tools.sns.naver_cafe_publisher import NaverCafePublisher
#     _NAVER_CAFE_AVAILABLE = True
# except ImportError:
NaverCafePublisher = None
_NAVER_CAFE_AVAILABLE = False

try:
    from src.tools.sns.naver_blog_publisher import NaverBlogPublisher
    _NAVER_BLOG_AVAILABLE = True
except ImportError:
    NaverBlogPublisher = None
    _NAVER_BLOG_AVAILABLE = False

try:
    from src.tools.sns.daum_cafe_publisher import DaumCafePublisher
    _DAUM_CAFE_AVAILABLE = True
except ImportError:
    DaumCafePublisher = None
    _DAUM_CAFE_AVAILABLE = False

if TYPE_CHECKING:
    from src.llm.router import ModelRouter

logger = logging.getLogger("corthex.sns.manager")

# 퍼블리싱 실행 권한이 있는 역할 (CMO 이상)
PUBLISH_ROLES = {"cmo_manager", "chief_of_staff"}

# 서버사이드 플랫폼 허용 목록 — 여기 없는 플랫폼은 submit 자체가 차단됨
ALLOWED_PLATFORMS = {"tistory", "youtube", "naver_blog", "daum_cafe"}
BLOCKED_PLATFORM_MSG = {
    "instagram": "비즈니스 계정 전환 전까지 잠금",
    "naver_cafe": "대표님 사용 안 함 (삭제)",
    "linkedin": "사용 안 함 (삭제)",
    "twitter": "사용 안 함",
    "facebook": "사용 안 함",
    "threads": "사용 안 함",
}

# DB 저장 키 (SQLite settings 테이블)
_DB_KEY = "sns_publish_queue"


def _db_save(data: list) -> None:
    """sns 큐를 SQLite DB에 저장 (배포 시 날아가지 않음)."""
    try:
        from db import save_setting
        save_setting(_DB_KEY, data)
    except ImportError:
        try:
            from web.db import save_setting
            save_setting(_DB_KEY, data)
        except ImportError:
            logger.warning("[SNS] DB 저장 실패: db 모듈을 찾을 수 없음")


def _db_load() -> list:
    """SNS 큐를 SQLite DB에서 로드."""
    try:
        from db import load_setting
        return load_setting(_DB_KEY, []) or []
    except ImportError:
        try:
            from web.db import load_setting
            return load_setting(_DB_KEY, []) or []
        except ImportError:
            return []


class SNSPublishRequest:
    """CEO 승인 대기 중인 퍼블리싱 요청."""

    def __init__(
        self,
        request_id: str = "",
        platform: str = "",
        content: dict[str, Any] | None = None,
        requested_by: str = "",
        status: str = "pending",  # pending → approved → published / rejected
        created_at: float = 0,
        approved_at: float = 0,
        published_at: float = 0,
        result: dict[str, Any] | None = None,
    ) -> None:
        self.request_id = request_id or str(uuid.uuid4())[:8]
        self.platform = platform
        self.content = content or {}
        self.requested_by = requested_by
        self.status = status
        self.created_at = created_at or time.time()
        self.approved_at = approved_at
        self.published_at = published_at
        self.result = result

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "platform": self.platform,
            "content": self.content,
            "requested_by": self.requested_by,
            "status": self.status,
            "created_at": self.created_at,
            "approved_at": self.approved_at,
            "published_at": self.published_at,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SNSPublishRequest:
        return cls(**data)


class SNSManager(BaseTool):
    """
    SNS 통합 관리 도구.

    에이전트가 이 도구를 통해 SNS 작업을 수행합니다.
    - submit: 콘텐츠 발행 요청 (승인 큐에 등록)
    - approve: CEO가 승인 (approved 상태로 변경)
    - reject: CEO가 거절
    - publish: 승인된 요청을 실제 퍼블리싱 (CMO 이상만 실행 가능)
    - status: 연결 상태 조회
    - queue: 승인 대기 큐 조회
    """

    def __init__(self, config: Any, model_router: ModelRouter) -> None:
        super().__init__(config, model_router)
        self.oauth = OAuthManager()
        self._publishers = {}
        if TistoryPublisher is not None:
            self._publishers["tistory"] = TistoryPublisher(self.oauth)
        if YouTubePublisher is not None:
            self._publishers["youtube"] = YouTubePublisher(self.oauth)
        if InstagramPublisher is not None:
            self._publishers["instagram"] = InstagramPublisher(self.oauth)
        if NaverCafePublisher is not None:
            self._publishers["naver_cafe"] = NaverCafePublisher(self.oauth)
        if NaverBlogPublisher is not None:
            self._publishers["naver_blog"] = NaverBlogPublisher(self.oauth)
        if DaumCafePublisher is not None:
            self._publishers["daum_cafe"] = DaumCafePublisher(self.oauth)
        self._queue: list[SNSPublishRequest] = []
        self._load_queue()

    # ── 큐 저장/로드 ──

    def _load_queue(self) -> None:
        try:
            raw = _db_load()
            self._queue = [SNSPublishRequest.from_dict(r) for r in raw]
        except (KeyError, TypeError):
            self._queue = []

    def _save_queue(self) -> None:
        _db_save([r.to_dict() for r in self._queue])

    # ── 메인 실행 ──

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "status")
        caller_id = kwargs.get("caller_id", "")

        if action == "submit":
            return await self._handle_submit(kwargs, caller_id)
        elif action == "approve":
            return self._handle_approve(kwargs)
        elif action == "reject":
            return self._handle_reject(kwargs)
        elif action == "publish":
            return await self._handle_publish(kwargs, caller_id)
        elif action == "queue":
            return self._handle_queue()
        elif action == "status":
            return self._handle_status()
        elif action == "auth_url":
            return self._handle_auth_url(kwargs)
        elif action == "exchange_code":
            return await self._handle_exchange_code(kwargs)
        else:
            return {"error": f"알 수 없는 action: {action}"}

    # ── submit: 발행 요청 (승인 큐에 등록) ──

    async def _handle_submit(
        self, kwargs: dict[str, Any], caller_id: str,
    ) -> dict[str, Any]:
        platform = kwargs.get("platform", "")

        # 서버사이드 플랫폼 차단 (프롬프트 무시해도 코드가 막음)
        if platform not in ALLOWED_PLATFORMS:
            reason = BLOCKED_PLATFORM_MSG.get(platform, "허용되지 않은 플랫폼")
            logger.warning("[SNS] 차단된 플랫폼 submit 시도: %s (%s)", platform, reason)
            return {
                "error": f"차단된 플랫폼: {platform} ({reason}). "
                         f"허용 플랫폼: {sorted(ALLOWED_PLATFORMS)}",
            }

        if platform not in self._publishers:
            return {"error": f"미지원 플랫폼: {platform}. 지원: {list(self._publishers)}"}

        content_data = {
            "title": kwargs.get("title", ""),
            "body": kwargs.get("body", ""),
            "tags": kwargs.get("tags", []),
            "category": kwargs.get("category", ""),
            "visibility": kwargs.get("visibility", "public"),
            "media_urls": kwargs.get("media_urls", []),
            "extra": kwargs.get("extra", {}),
        }

        # LLM으로 콘텐츠 검토/요약 생성
        summary = await self._llm_call(
            system_prompt=(
                "당신은 SNS 콘텐츠 검토자입니다. "
                "아래 콘텐츠를 CEO에게 보고하기 위한 간결한 요약을 작성하세요.\n"
                "- 플랫폼, 제목, 핵심 내용 (2줄 이내)\n"
                "- 예상 타겟 독자\n"
                "- 발행 추천 여부와 이유"
            ),
            user_prompt=json.dumps(
                {"platform": platform, **content_data},
                ensure_ascii=False,
            ),
        )

        req = SNSPublishRequest(
            platform=platform,
            content=content_data,
            requested_by=caller_id,
        )
        self._queue.append(req)
        self._save_queue()

        logger.info(
            "[SNS] 발행 요청 등록: %s → %s (요청자: %s)",
            req.request_id, platform, caller_id,
        )

        return {
            "request_id": req.request_id,
            "status": "pending",
            "platform": platform,
            "summary": summary,
            "message": (
                f"CEO 승인 대기 중입니다.\n"
                f"요청 ID: {req.request_id}\n"
                f"승인 후 CMO가 퍼블리싱을 실행합니다."
            ),
        }

    # ── approve: CEO 승인 ──

    def _handle_approve(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        request_id = kwargs.get("request_id", "")
        req = self._find_request(request_id)
        if not req:
            return {"error": f"요청 ID를 찾을 수 없음: {request_id}"}

        if req.status != "pending":
            return {"error": f"이미 처리된 요청: {req.status}"}

        req.status = "approved"
        req.approved_at = time.time()
        self._save_queue()

        logger.info("[SNS] CEO 승인 완료: %s", request_id)
        return {
            "request_id": request_id,
            "status": "approved",
            "message": f"승인 완료. CMO가 퍼블리싱을 실행해주세요.",
            "platform": req.platform,
            "title": req.content.get("title", ""),
        }

    # ── reject: CEO 거절 ──

    def _handle_reject(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        request_id = kwargs.get("request_id", "")
        reason = kwargs.get("reason", "")
        req = self._find_request(request_id)
        if not req:
            return {"error": f"요청 ID를 찾을 수 없음: {request_id}"}

        req.status = "rejected"
        req.result = {"reason": reason}
        self._save_queue()

        logger.info("[SNS] CEO 거절: %s (사유: %s)", request_id, reason)
        return {
            "request_id": request_id,
            "status": "rejected",
            "reason": reason,
            "message": f"거절됨. 사유: {reason}",
        }

    # ── publish: 승인된 요청 실제 퍼블리싱 (CMO 이상만) ──

    async def _handle_publish(
        self, kwargs: dict[str, Any], caller_id: str,
    ) -> dict[str, Any]:
        # 권한 확인: CMO 이상만 퍼블리싱 가능
        if caller_id not in PUBLISH_ROLES:
            return {
                "error": (
                    f"퍼블리싱 권한 없음 (caller: {caller_id}). "
                    f"CMO 이상 직급만 실행 가능합니다: {PUBLISH_ROLES}"
                ),
            }

        request_id = kwargs.get("request_id", "")
        req = self._find_request(request_id)
        if not req:
            return {"error": f"요청 ID를 찾을 수 없음: {request_id}"}

        if req.status != "approved":
            return {"error": f"승인되지 않은 요청: {req.status}. CEO 승인이 필요합니다."}

        # 실제 퍼블리싱 실행
        publisher = self._publishers.get(req.platform)
        if not publisher:
            return {"error": f"퍼블리셔 없음: {req.platform}"}

        content = PostContent(**req.content)
        result = await publisher.publish(content)

        req.status = "published" if result.success else "failed"
        req.published_at = time.time()
        req.result = {
            "success": result.success,
            "post_id": result.post_id,
            "post_url": result.post_url,
            "message": result.message,
        }
        self._save_queue()

        return {
            "request_id": request_id,
            "status": req.status,
            "result": req.result,
            "message": result.message,
        }

    # ── queue: 승인 대기 큐 조회 ──

    def _handle_queue(self) -> dict[str, Any]:
        pending = [r.to_dict() for r in self._queue if r.status == "pending"]
        approved = [r.to_dict() for r in self._queue if r.status == "approved"]
        published = [r.to_dict() for r in self._queue if r.status == "published"]
        rejected = [r.to_dict() for r in self._queue if r.status == "rejected"]

        return {
            "pending": pending,
            "approved": approved,
            "published": published,
            "rejected": rejected,
            "total": len(self._queue),
            "summary": (
                f"대기 {len(pending)} / 승인 {len(approved)} / "
                f"발행 {len(published)} / 거절 {len(rejected)}"
            ),
        }

    # ── status: 연결 상태 ──

    # Selenium 기반 퍼블리셔 (OAuth 아닌 credential 로그인)
    _SELENIUM_PLATFORMS = {"tistory", "naver_blog", "daum_cafe"}

    def _handle_status(self) -> dict[str, Any]:
        platform_status = self.oauth.status()

        # Selenium 기반 퍼블리셔는 OAuth 상태가 아닌 credential 존재 여부로 표시
        for platform_name in self._SELENIUM_PLATFORMS:
            pub = self._publishers.get(platform_name)
            if pub:
                platform_status.append({
                    "platform": platform_name,
                    "connected": True,
                    "expired": False,
                    "has_refresh": False,
                    "auth_type": "selenium",
                })

        return {
            "platforms": platform_status,
            "queue_summary": self._handle_queue()["summary"],
        }

    # ── auth_url: OAuth 인증 URL 생성 ──

    def _handle_auth_url(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        platform = kwargs.get("platform", "")
        try:
            url = self.oauth.get_auth_url(platform)
            return {"platform": platform, "auth_url": url}
        except ValueError as e:
            return {"error": str(e)}

    # ── exchange_code: OAuth 코드 교환 ──

    async def _handle_exchange_code(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        platform = kwargs.get("platform", "")
        code = kwargs.get("code", "")
        try:
            token = await self.oauth.exchange_code(platform, code)
            return {
                "platform": platform,
                "connected": True,
                "message": f"{platform} 연결 완료",
            }
        except Exception as e:
            return {"error": str(e)}

    # ── 유틸 ──

    def _find_request(self, request_id: str) -> SNSPublishRequest | None:
        for r in self._queue:
            if r.request_id == request_id:
                return r
        return None
