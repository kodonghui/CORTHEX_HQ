"""
Instagram 퍼블리셔.

Instagram Graph API를 통해 피드/릴스를 자동으로 게시합니다.
- 이미지 게시물 (단일/캐러셀)
- 릴스 (동영상)
- 게시물 조회/삭제
주의: Instagram API는 비즈니스/크리에이터 계정 + Facebook 페이지 연동이 필요합니다.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

from src.tools.sns.base_publisher import BasePublisher, PostContent, PublishResult

logger = logging.getLogger("corthex.sns.instagram")

GRAPH_API = "https://graph.instagram.com/v21.0"


class InstagramPublisher(BasePublisher):
    """Instagram Graph API 기반 퍼블리셔.

    인증: INSTAGRAM_ACCESS_TOKEN 환경변수를 직접 사용 (OAuth 흐름 불필요).
    User ID: INSTAGRAM_USER_ID가 없으면 토큰으로 자동 조회.
    """

    platform = "instagram"

    def __init__(self, oauth: Any = None) -> None:
        # OAuth 매니저 없이도 동작 (환경변수 토큰 직접 사용)
        if oauth is not None:
            super().__init__(oauth)
        self._cached_user_id: str = ""
        self._resolved_uid: str = ""

    def _get_access_token(self) -> str:
        """환경변수에서 Instagram 액세스 토큰을 가져온다."""
        return os.getenv("INSTAGRAM_ACCESS_TOKEN", "")

    async def _resolve_user_id(self) -> str:
        """INSTAGRAM_USER_ID 환경변수 또는 토큰으로 자동 조회."""
        env_id = os.getenv("INSTAGRAM_USER_ID", "")
        if env_id:
            return env_id
        if self._cached_user_id:
            return self._cached_user_id
        # 토큰으로 User ID 자동 조회
        token = self._get_access_token()
        if not token:
            return ""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{GRAPH_API}/me",
                    params={"fields": "id,username", "access_token": token},
                )
                data = resp.json()
                uid = data.get("id", "")
                if uid:
                    self._cached_user_id = uid
                    uname = data.get("username", "")
                    logger.info("[Instagram] User ID 자동 조회 성공: %s (@%s)", uid, uname)
                return uid
        except Exception as e:
            logger.error("[Instagram] User ID 조회 실패: %s", e)
            return ""

    async def _api_call(
        self, endpoint: str, method: str = "POST", **params: Any
    ) -> dict[str, Any]:
        token = self._get_access_token()
        if not token:
            return {"error": "INSTAGRAM_ACCESS_TOKEN 환경변수가 설정되지 않았습니다."}
        params["access_token"] = token

        async with httpx.AsyncClient(timeout=30) as client:
            url = f"{GRAPH_API}/{endpoint}"
            if method == "GET":
                resp = await client.get(url, params=params)
            else:
                resp = await client.post(url, data=params)
            return resp.json()

    async def publish(self, content: PostContent) -> PublishResult:
        """이미지 또는 릴스를 Instagram에 게시."""
        token = self._get_access_token()
        if not token:
            return PublishResult(
                success=False,
                platform="instagram",
                message="INSTAGRAM_ACCESS_TOKEN 환경변수가 설정되지 않았습니다.",
            )

        ig_user_id = await self._resolve_user_id()
        if not ig_user_id:
            return PublishResult(
                success=False,
                platform="instagram",
                message="Instagram User ID를 가져올 수 없습니다. INSTAGRAM_ACCESS_TOKEN을 확인하세요.",
            )

        media_urls = content.media_urls
        if not media_urls:
            return PublishResult(
                success=False,
                platform="instagram",
                message="이미지 또는 동영상 URL이 필요합니다 (media_urls).",
            )

        is_video = content.extra.get("media_type") == "REELS"
        caption = self._build_caption(content)

        # ig_user_id를 내부 메서드에서 사용할 수 있도록 캐시
        self._resolved_uid = ig_user_id

        if len(media_urls) > 1 and not is_video:
            return await self._publish_carousel(media_urls, caption)

        return await self._publish_single(media_urls[0], caption, is_video)

    def _build_caption(self, content: PostContent) -> str:
        parts = []
        if content.title:
            parts.append(content.title)
        if content.body:
            parts.append(content.body)
        if content.tags:
            hashtags = " ".join(f"#{t}" for t in content.tags)
            parts.append(hashtags)
        return "\n\n".join(parts)

    async def _publish_single(
        self, media_url: str, caption: str, is_video: bool = False,
    ) -> PublishResult:
        # 1단계: 미디어 컨테이너 생성
        params: dict[str, Any] = {"caption": caption}
        if is_video:
            params["media_type"] = "REELS"
            params["video_url"] = media_url
        else:
            params["image_url"] = media_url

        container = await self._api_call(
            f"{self._resolved_uid}/media", **params
        )
        container_id = container.get("id")
        if not container_id:
            return PublishResult(
                success=False, platform="instagram",
                message=f"미디어 컨테이너 생성 실패: {container}",
                raw_response=container,
            )

        # 동영상은 처리 시간 대기
        if is_video:
            await self._wait_for_processing(container_id)

        # 2단계: 게시
        result = await self._api_call(
            f"{self._resolved_uid}/media_publish",
            creation_id=container_id,
        )

        post_id = result.get("id", "")
        if post_id:
            logger.info("[Instagram] 게시 성공: %s", post_id)
            return PublishResult(
                success=True, platform="instagram",
                post_id=post_id,
                post_url=f"https://www.instagram.com/p/{post_id}/",
                message="Instagram 게시 완료",
                raw_response=result,
            )

        return PublishResult(
            success=False, platform="instagram",
            message=f"게시 실패: {result}", raw_response=result,
        )

    async def _publish_carousel(
        self, media_urls: list[str], caption: str,
    ) -> PublishResult:
        # 1단계: 각 이미지의 컨테이너 생성
        children_ids = []
        for url in media_urls[:10]:  # 최대 10개
            container = await self._api_call(
                f"{self._resolved_uid}/media",
                image_url=url,
                is_carousel_item="true",
            )
            cid = container.get("id")
            if cid:
                children_ids.append(cid)

        if not children_ids:
            return PublishResult(
                success=False, platform="instagram",
                message="캐러셀 아이템 생성 실패",
            )

        # 2단계: 캐러셀 컨테이너 생성
        carousel = await self._api_call(
            f"{self._resolved_uid}/media",
            media_type="CAROUSEL",
            caption=caption,
            children=",".join(children_ids),
        )
        carousel_id = carousel.get("id")
        if not carousel_id:
            return PublishResult(
                success=False, platform="instagram",
                message=f"캐러셀 생성 실패: {carousel}",
            )

        # 3단계: 게시
        result = await self._api_call(
            f"{self._resolved_uid}/media_publish",
            creation_id=carousel_id,
        )

        post_id = result.get("id", "")
        if post_id:
            logger.info("[Instagram] 캐러셀 게시 성공: %s", post_id)
            return PublishResult(
                success=True, platform="instagram",
                post_id=post_id,
                post_url=f"https://www.instagram.com/p/{post_id}/",
                message=f"Instagram 캐러셀 게시 완료 ({len(children_ids)}장)",
                raw_response=result,
            )

        return PublishResult(
            success=False, platform="instagram",
            message=f"캐러셀 게시 실패: {result}", raw_response=result,
        )

    async def _wait_for_processing(
        self, container_id: str, max_wait: int = 120,
    ) -> None:
        """동영상 처리 완료 대기."""
        for _ in range(max_wait // 5):
            status = await self._api_call(
                container_id, method="GET",
                fields="status_code",
            )
            if status.get("status_code") == "FINISHED":
                return
            if status.get("status_code") == "ERROR":
                raise RuntimeError(f"Instagram 동영상 처리 실패: {status}")
            await asyncio.sleep(5)
        raise RuntimeError("Instagram 동영상 처리 시간 초과")

    async def delete(self, post_id: str) -> bool:
        # Instagram Graph API는 직접 삭제를 지원하지 않음 (Facebook 관리자 통해 삭제)
        logger.warning("[Instagram] API를 통한 직접 삭제는 지원되지 않습니다.")
        return False

    async def get_recent_media(self, limit: int = 10) -> list[dict[str, Any]]:
        data = await self._api_call(
            f"{self._resolved_uid}/media", method="GET",
            fields="id,caption,media_type,timestamp,permalink",
            limit=str(limit),
        )
        return data.get("data", [])
