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
    """Instagram Graph API 기반 퍼블리셔."""

    platform = "instagram"

    @property
    def ig_user_id(self) -> str:
        return os.getenv("INSTAGRAM_USER_ID", "")

    async def _api_call(
        self, endpoint: str, method: str = "POST", **params: Any
    ) -> dict[str, Any]:
        token = await self._get_token()
        params["access_token"] = token

        async with httpx.AsyncClient() as client:
            url = f"{GRAPH_API}/{endpoint}"
            if method == "GET":
                resp = await client.get(url, params=params)
            else:
                resp = await client.post(url, data=params)
            return resp.json()

    async def publish(self, content: PostContent) -> PublishResult:
        """이미지 또는 릴스를 Instagram에 게시."""
        if not self.ig_user_id:
            return PublishResult(
                success=False,
                platform="instagram",
                message="INSTAGRAM_USER_ID 환경변수가 필요합니다.",
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
            f"{self.ig_user_id}/media", **params
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
            f"{self.ig_user_id}/media_publish",
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
                f"{self.ig_user_id}/media",
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
            f"{self.ig_user_id}/media",
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
            f"{self.ig_user_id}/media_publish",
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
            f"{self.ig_user_id}/media", method="GET",
            fields="id,caption,media_type,timestamp,permalink",
            limit=str(limit),
        )
        return data.get("data", [])
