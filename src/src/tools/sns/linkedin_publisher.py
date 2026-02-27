"""
LinkedIn 퍼블리셔.

LinkedIn Marketing API를 통해 게시물을 자동으로 작성합니다.
- 텍스트 게시물
- 이미지 첨부 게시물
- 기사 공유 (링크 포스트)
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from src.tools.sns.base_publisher import BasePublisher, PostContent, PublishResult

logger = logging.getLogger("corthex.sns.linkedin")

LINKEDIN_API = "https://api.linkedin.com/v2"
LINKEDIN_REST_API = "https://api.linkedin.com/rest"


class LinkedInPublisher(BasePublisher):
    """LinkedIn 게시물 퍼블리셔."""

    platform = "linkedin"

    @property
    def person_urn(self) -> str:
        """LinkedIn 사용자 URN (urn:li:person:XXXX)."""
        member_id = os.getenv("LINKEDIN_MEMBER_ID", "")
        if member_id:
            return f"urn:li:person:{member_id}"
        return ""

    async def _headers(self) -> dict[str, str]:
        token = await self._get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": "202401",
        }

    async def publish(self, content: PostContent) -> PublishResult:
        if not self.person_urn:
            return PublishResult(
                success=False, platform="linkedin",
                message="LINKEDIN_MEMBER_ID 환경변수가 필요합니다.",
            )

        # 링크 포스트
        link_url = content.extra.get("link_url", "")
        if link_url:
            return await self._publish_article(content, link_url)

        # 이미지 포스트
        if content.media_urls:
            return await self._publish_with_image(content)

        # 텍스트 포스트
        return await self._publish_text(content)

    async def _publish_text(self, content: PostContent) -> PublishResult:
        text = self._build_text(content)

        body = {
            "author": self.person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                },
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
            },
        }

        return await self._do_post(body)

    async def _publish_article(
        self, content: PostContent, link_url: str,
    ) -> PublishResult:
        text = self._build_text(content)

        body = {
            "author": self.person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "ARTICLE",
                    "media": [
                        {
                            "status": "READY",
                            "originalUrl": link_url,
                            "title": {"text": content.title},
                            "description": {"text": content.body[:200]},
                        }
                    ],
                },
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
            },
        }

        return await self._do_post(body)

    async def _publish_with_image(self, content: PostContent) -> PublishResult:
        headers = await self._headers()

        # 1단계: 이미지 업로드 등록
        register_body = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": self.person_urn,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent",
                    }
                ],
            }
        }

        async with httpx.AsyncClient() as client:
            reg_resp = await client.post(
                f"{LINKEDIN_API}/assets?action=registerUpload",
                headers=headers,
                json=register_body,
            )
            reg_data = reg_resp.json()

        upload_info = reg_data.get("value", {})
        upload_url = (
            upload_info
            .get("uploadMechanism", {})
            .get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {})
            .get("uploadUrl", "")
        )
        asset = upload_info.get("asset", "")

        if not upload_url or not asset:
            return PublishResult(
                success=False, platform="linkedin",
                message=f"이미지 업로드 등록 실패: {reg_data}",
            )

        # 2단계: 이미지 바이너리 업로드
        image_url = content.media_urls[0]
        async with httpx.AsyncClient() as client:
            img_resp = await client.get(image_url)
            img_data = img_resp.content

            await client.put(
                upload_url,
                headers={
                    "Authorization": headers["Authorization"],
                    "Content-Type": "application/octet-stream",
                },
                content=img_data,
            )

        # 3단계: 게시물 작성
        text = self._build_text(content)
        body = {
            "author": self.person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "IMAGE",
                    "media": [
                        {
                            "status": "READY",
                            "media": asset,
                            "title": {"text": content.title},
                        }
                    ],
                },
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
            },
        }

        return await self._do_post(body)

    async def _do_post(self, body: dict[str, Any]) -> PublishResult:
        headers = await self._headers()

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{LINKEDIN_API}/ugcPosts",
                headers=headers,
                json=body,
            )

            if resp.status_code == 201:
                post_id = resp.headers.get("X-RestLi-Id", "")
                logger.info("[LinkedIn] 게시 성공: %s", post_id)
                return PublishResult(
                    success=True, platform="linkedin",
                    post_id=post_id,
                    post_url=f"https://www.linkedin.com/feed/update/{post_id}/",
                    message="LinkedIn 게시 완료",
                )

            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}

            error = data.get("message", str(data))
            logger.error("[LinkedIn] 게시 실패: %s", error)
            return PublishResult(
                success=False, platform="linkedin",
                message=f"게시 실패: {error}", raw_response=data,
            )

    def _build_text(self, content: PostContent) -> str:
        parts = []
        if content.title:
            parts.append(content.title)
        if content.body:
            parts.append(content.body)
        if content.tags:
            hashtags = " ".join(f"#{t}" for t in content.tags)
            parts.append(hashtags)
        return "\n\n".join(parts)

    async def delete(self, post_id: str) -> bool:
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{LINKEDIN_API}/ugcPosts/{post_id}",
                headers=headers,
            )
        return resp.status_code == 204

    async def get_profile(self) -> dict[str, Any]:
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{LINKEDIN_API}/userinfo",
                headers=headers,
            )
            return resp.json()
