"""
YouTube 퍼블리셔.

YouTube Data API v3를 통해 동영상 업로드 및 관리를 수행합니다.
- 동영상 메타데이터 업데이트 (제목, 설명, 태그)
- 커뮤니티 게시글 관리
- 동영상 공개 상태 변경
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from src.tools.sns.base_publisher import BasePublisher, PostContent, PublishResult

logger = logging.getLogger("corthex.sns.youtube")

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
YOUTUBE_UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3/videos"


class YouTubePublisher(BasePublisher):
    """YouTube 동영상/커뮤니티 퍼블리셔."""

    platform = "youtube"

    async def _headers(self) -> dict[str, str]:
        token = await self._get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def publish(self, content: PostContent) -> PublishResult:
        """동영상 메타데이터 업데이트 또는 신규 업로드 초기화.

        media_urls[0]에 로컬 파일 경로가 있으면 resumable upload를 시작하고,
        없으면 메타데이터만 설정합니다.
        """
        visibility_map = {"public": "public", "private": "private", "draft": "unlisted"}
        privacy = visibility_map.get(content.visibility, "private")

        body = {
            "snippet": {
                "title": content.title,
                "description": content.body,
                "tags": content.tags,
                "categoryId": content.extra.get("category_id", "22"),
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        headers = await self._headers()

        # 파일 업로드가 필요한 경우 → resumable upload 시작
        if content.media_urls:
            video_path = content.media_urls[0]
            return await self._resumable_upload(video_path, body, headers)

        # 메타데이터만 업데이트 (기존 영상 수정)
        video_id = content.extra.get("video_id", "")
        if not video_id:
            return PublishResult(
                success=False,
                platform="youtube",
                message="video_id 또는 media_urls 필요",
            )

        body["id"] = video_id
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                f"{YOUTUBE_API}/videos",
                params={"part": "snippet,status"},
                headers=headers,
                json=body,
            )
            data = resp.json()

        if "id" in data:
            vid = data["id"]
            url = f"https://youtu.be/{vid}"
            logger.info("[YouTube] 영상 업데이트 성공: %s", url)
            return PublishResult(
                success=True,
                platform="youtube",
                post_id=vid,
                post_url=url,
                message="YouTube 영상 메타데이터 업데이트 완료",
                raw_response=data,
            )

        error = data.get("error", {}).get("message", str(data))
        logger.error("[YouTube] 업데이트 실패: %s", error)
        return PublishResult(
            success=False, platform="youtube",
            message=f"업데이트 실패: {error}", raw_response=data,
        )

    async def _resumable_upload(
        self, video_path: str, metadata: dict, headers: dict[str, str],
    ) -> PublishResult:
        """Resumable upload으로 동영상 업로드."""
        upload_headers = {
            "Authorization": headers["Authorization"],
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/*",
        }

        async with httpx.AsyncClient(timeout=600) as client:
            # 1단계: 업로드 세션 시작
            init_resp = await client.post(
                YOUTUBE_UPLOAD_API,
                params={"uploadType": "resumable", "part": "snippet,status"},
                headers=upload_headers,
                json=metadata,
            )

            if init_resp.status_code != 200:
                return PublishResult(
                    success=False, platform="youtube",
                    message=f"업로드 세션 시작 실패: {init_resp.text}",
                )

            upload_url = init_resp.headers.get("Location", "")
            if not upload_url:
                return PublishResult(
                    success=False, platform="youtube",
                    message="업로드 URL을 받지 못했습니다.",
                )

            # 2단계: 파일 전송
            with open(video_path, "rb") as f:
                video_data = f.read()

            upload_resp = await client.put(
                upload_url,
                headers={"Content-Type": "video/*"},
                content=video_data,
            )
            data = upload_resp.json()

        if "id" in data:
            vid = data["id"]
            url = f"https://youtu.be/{vid}"
            logger.info("[YouTube] 영상 업로드 성공: %s", url)
            return PublishResult(
                success=True, platform="youtube",
                post_id=vid, post_url=url,
                message="YouTube 영상 업로드 완료",
                raw_response=data,
            )

        error = data.get("error", {}).get("message", str(data))
        return PublishResult(
            success=False, platform="youtube",
            message=f"업로드 실패: {error}", raw_response=data,
        )

    async def delete(self, post_id: str) -> bool:
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{YOUTUBE_API}/videos",
                params={"id": post_id},
                headers=headers,
            )
        return resp.status_code == 204

    async def get_my_channel(self) -> dict[str, Any]:
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{YOUTUBE_API}/channels",
                params={"part": "snippet,statistics", "mine": "true"},
                headers=headers,
            )
        data = resp.json()
        items = data.get("items", [])
        return items[0] if items else {}
