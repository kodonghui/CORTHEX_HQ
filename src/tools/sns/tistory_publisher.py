"""
Tistory 블로그 퍼블리셔.

Tistory Open API를 통해 블로그 글을 자동으로 작성·수정·삭제합니다.
- 글 작성 (HTML 본문 지원)
- 카테고리/태그 설정
- 공개/비공개/보호 설정
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from src.tools.sns.base_publisher import BasePublisher, PostContent, PublishResult

logger = logging.getLogger("corthex.sns.tistory")

TISTORY_API = "https://www.tistory.com/apis"


class TistoryPublisher(BasePublisher):
    """Tistory 블로그 자동 퍼블리셔."""

    platform = "tistory"

    @property
    def blog_name(self) -> str:
        return os.getenv("TISTORY_BLOG_NAME", "")

    async def _api_call(
        self, endpoint: str, method: str = "POST", **params: Any
    ) -> dict[str, Any]:
        token = await self._get_token()
        params["access_token"] = token
        params["output"] = "json"
        if self.blog_name:
            params.setdefault("blogName", self.blog_name)

        async with httpx.AsyncClient() as client:
            url = f"{TISTORY_API}/{endpoint}"
            if method == "GET":
                resp = await client.get(url, params=params)
            else:
                resp = await client.post(url, data=params)
            return resp.json()

    async def publish(self, content: PostContent) -> PublishResult:
        visibility_map = {"public": "3", "protected": "1", "private": "0", "draft": "0"}

        params: dict[str, Any] = {
            "title": content.title,
            "content": content.body,
            "visibility": visibility_map.get(content.visibility, "3"),
        }
        if content.tags:
            params["tag"] = ",".join(content.tags)
        if content.category:
            params["category"] = content.category

        data = await self._api_call("post/write", **params)

        tistory = data.get("tistory", {})
        if tistory.get("status") == "200":
            post_id = str(tistory.get("postId", ""))
            post_url = tistory.get("url", "")
            logger.info("[Tistory] 글 발행 성공: %s", post_url)
            return PublishResult(
                success=True,
                platform="tistory",
                post_id=post_id,
                post_url=post_url,
                message="Tistory 글 발행 완료",
                raw_response=data,
            )

        error_msg = tistory.get("error_message", str(data))
        logger.error("[Tistory] 글 발행 실패: %s", error_msg)
        return PublishResult(
            success=False,
            platform="tistory",
            message=f"발행 실패: {error_msg}",
            raw_response=data,
        )

    async def delete(self, post_id: str) -> bool:
        data = await self._api_call("post/delete", postId=post_id)
        return data.get("tistory", {}).get("status") == "200"

    async def get_categories(self) -> list[dict[str, str]]:
        data = await self._api_call("category/list", method="GET")
        categories = data.get("tistory", {}).get("item", {}).get("categories", [])
        return [{"id": c["id"], "name": c["name"]} for c in categories]

    async def get_posts(self, page: int = 1) -> list[dict[str, Any]]:
        data = await self._api_call("post/list", method="GET", page=str(page))
        posts = data.get("tistory", {}).get("item", {}).get("posts", [])
        return posts
