"""
CORTHEX HQ — SNS 자동 발행 (Instagram Graph API + YouTube Data API v3)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "sns.yaml"


@dataclass
class PublishResult:
    platform: str
    success: bool
    post_id: str = ""
    url: str = ""
    error: str = ""


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


# ──────────────────────────────────────────────
#  Instagram Graph API
# ──────────────────────────────────────────────

class InstagramPublisher:
    """Instagram Graph API를 통한 콘텐츠 발행."""

    BASE = "https://graph.instagram.com/v21.0"

    def __init__(self) -> None:
        cfg = _load_config().get("instagram", {})
        self.enabled = cfg.get("enabled", False)
        self.access_token = os.getenv(cfg.get("access_token_env", ""), "")
        self.ig_user_id = os.getenv(cfg.get("ig_user_id_env", ""), "")
        self.daily_limit = cfg.get("daily_limit", 20)

    async def publish_photo(
        self,
        image_url: str,
        caption: str = "",
    ) -> PublishResult:
        """사진 게시물 발행 (URL 기반)."""
        if not self.enabled:
            return PublishResult("instagram", False, error="Instagram 연동이 비활성화 상태입니다. config/sns.yaml에서 enabled: true로 변경하세요.")
        if not self.access_token or not self.ig_user_id:
            return PublishResult("instagram", False, error="Instagram 자격증명이 설정되지 않았습니다 (INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_USER_ID).")

        async with httpx.AsyncClient(timeout=60) as client:
            # Step 1: 미디어 컨테이너 생성
            create_resp = await client.post(
                f"{self.BASE}/{self.ig_user_id}/media",
                params={
                    "image_url": image_url,
                    "caption": caption,
                    "access_token": self.access_token,
                },
            )
            create_data = create_resp.json()
            if "id" not in create_data:
                return PublishResult(
                    "instagram", False,
                    error=f"컨테이너 생성 실패: {create_data.get('error', {}).get('message', str(create_data))}",
                )
            container_id = create_data["id"]

            # Step 2: 컨테이너 상태 확인 (최대 30초 대기)
            import asyncio
            for _ in range(6):
                status_resp = await client.get(
                    f"{self.BASE}/{container_id}",
                    params={"fields": "status_code", "access_token": self.access_token},
                )
                status = status_resp.json().get("status_code")
                if status == "FINISHED":
                    break
                if status == "ERROR":
                    return PublishResult("instagram", False, error="미디어 처리 실패")
                await asyncio.sleep(5)

            # Step 3: 발행
            publish_resp = await client.post(
                f"{self.BASE}/{self.ig_user_id}/media_publish",
                params={
                    "creation_id": container_id,
                    "access_token": self.access_token,
                },
            )
            pub_data = publish_resp.json()
            if "id" in pub_data:
                post_id = pub_data["id"]
                return PublishResult(
                    "instagram", True,
                    post_id=post_id,
                    url=f"https://www.instagram.com/p/{post_id}/",
                )
            return PublishResult(
                "instagram", False,
                error=f"발행 실패: {pub_data.get('error', {}).get('message', str(pub_data))}",
            )

    async def publish_reel(
        self,
        video_url: str,
        caption: str = "",
    ) -> PublishResult:
        """릴스 발행 (URL 기반)."""
        if not self.enabled:
            return PublishResult("instagram", False, error="Instagram 연동이 비활성화 상태입니다.")
        if not self.access_token or not self.ig_user_id:
            return PublishResult("instagram", False, error="Instagram 자격증명 미설정.")

        async with httpx.AsyncClient(timeout=120) as client:
            create_resp = await client.post(
                f"{self.BASE}/{self.ig_user_id}/media",
                params={
                    "media_type": "REELS",
                    "video_url": video_url,
                    "caption": caption,
                    "access_token": self.access_token,
                },
            )
            create_data = create_resp.json()
            if "id" not in create_data:
                return PublishResult("instagram", False, error=f"릴스 컨테이너 생성 실패: {create_data}")
            container_id = create_data["id"]

            import asyncio
            for _ in range(24):  # 릴스는 처리 시간이 더 걸림 (최대 2분)
                status_resp = await client.get(
                    f"{self.BASE}/{container_id}",
                    params={"fields": "status_code", "access_token": self.access_token},
                )
                status = status_resp.json().get("status_code")
                if status == "FINISHED":
                    break
                if status == "ERROR":
                    return PublishResult("instagram", False, error="릴스 처리 실패")
                await asyncio.sleep(5)

            publish_resp = await client.post(
                f"{self.BASE}/{self.ig_user_id}/media_publish",
                params={"creation_id": container_id, "access_token": self.access_token},
            )
            pub_data = publish_resp.json()
            if "id" in pub_data:
                return PublishResult("instagram", True, post_id=pub_data["id"])
            return PublishResult("instagram", False, error=f"릴스 발행 실패: {pub_data}")


# ──────────────────────────────────────────────
#  YouTube Data API v3
# ──────────────────────────────────────────────

class YouTubePublisher:
    """YouTube Data API v3를 통한 동영상 업로드."""

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"

    def __init__(self) -> None:
        cfg = _load_config().get("youtube", {})
        self.enabled = cfg.get("enabled", False)
        self.client_id = os.getenv(cfg.get("client_id_env", ""), "")
        self.client_secret = os.getenv(cfg.get("client_secret_env", ""), "")
        self.refresh_token = os.getenv(cfg.get("refresh_token_env", ""), "")
        self.daily_limit = cfg.get("daily_upload_limit", 5)
        self._access_token: str = ""

    async def _ensure_token(self) -> str:
        """OAuth2 refresh token으로 access token 갱신."""
        if self._access_token:
            return self._access_token
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            data = resp.json()
            self._access_token = data.get("access_token", "")
            return self._access_token

    async def upload_video(
        self,
        file_path: str,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        privacy: str = "private",
        category_id: str = "22",  # People & Blogs
    ) -> PublishResult:
        """동영상 업로드 (resumable upload)."""
        if not self.enabled:
            return PublishResult("youtube", False, error="YouTube 연동이 비활성화 상태입니다. config/sns.yaml에서 enabled: true로 변경하세요.")
        if not self.client_id or not self.client_secret or not self.refresh_token:
            return PublishResult("youtube", False, error="YouTube 자격증명 미설정 (YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN).")

        video_file = Path(file_path)
        if not video_file.exists():
            return PublishResult("youtube", False, error=f"파일을 찾을 수 없습니다: {file_path}")

        token = await self._ensure_token()
        if not token:
            return PublishResult("youtube", False, error="YouTube OAuth2 토큰 갱신 실패.")

        import json
        metadata = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags or [],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        async with httpx.AsyncClient(timeout=600) as client:
            # Step 1: Resumable upload 시작
            init_resp = await client.post(
                f"{self.UPLOAD_URL}?uploadType=resumable&part=snippet,status",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Type": "video/*",
                    "X-Upload-Content-Length": str(video_file.stat().st_size),
                },
                content=json.dumps(metadata),
            )
            if init_resp.status_code not in (200, 308):
                return PublishResult("youtube", False, error=f"업로드 초기화 실패: {init_resp.status_code} {init_resp.text}")

            upload_url = init_resp.headers.get("Location", "")
            if not upload_url:
                return PublishResult("youtube", False, error="업로드 URL을 받지 못했습니다.")

            # Step 2: 동영상 파일 업로드
            video_data = video_file.read_bytes()
            upload_resp = await client.put(
                upload_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "video/*",
                },
                content=video_data,
            )
            if upload_resp.status_code == 200:
                data = upload_resp.json()
                video_id = data.get("id", "")
                return PublishResult(
                    "youtube", True,
                    post_id=video_id,
                    url=f"https://youtu.be/{video_id}",
                )
            return PublishResult("youtube", False, error=f"업로드 실패: {upload_resp.status_code} {upload_resp.text}")


# ──────────────────────────────────────────────
#  통합 SNS Publisher
# ──────────────────────────────────────────────

class SNSPublisher:
    """Instagram + YouTube 통합 발행 관리."""

    def __init__(self) -> None:
        self.instagram = InstagramPublisher()
        self.youtube = YouTubePublisher()

    def get_status(self) -> dict:
        """각 플랫폼 연동 상태 반환."""
        return {
            "instagram": {
                "enabled": self.instagram.enabled,
                "configured": bool(self.instagram.access_token and self.instagram.ig_user_id),
            },
            "youtube": {
                "enabled": self.youtube.enabled,
                "configured": bool(self.youtube.client_id and self.youtube.refresh_token),
            },
        }

    async def publish_instagram_photo(self, image_url: str, caption: str = "") -> PublishResult:
        return await self.instagram.publish_photo(image_url, caption)

    async def publish_instagram_reel(self, video_url: str, caption: str = "") -> PublishResult:
        return await self.instagram.publish_reel(video_url, caption)

    async def publish_youtube_video(
        self, file_path: str, title: str, description: str = "",
        tags: list[str] | None = None, privacy: str = "private",
    ) -> PublishResult:
        return await self.youtube.upload_video(file_path, title, description, tags, privacy)
