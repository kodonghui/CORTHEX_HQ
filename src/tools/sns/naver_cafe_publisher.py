"""
네이버 카페 퍼블리셔.

네이버 Open API를 통해 카페 게시글을 자동으로 작성합니다.
- 카페 게시글 작성 (HTML 본문 지원)
- 공개/비공개 설정
- clubid/menuid는 환경변수 또는 PostContent.extra로 지정
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from src.tools.sns.base_publisher import BasePublisher, PostContent, PublishResult

logger = logging.getLogger("corthex.sns.naver_cafe")

NAVER_CAFE_API = "https://openapi.naver.com/v1/cafe"


class NaverCafePublisher(BasePublisher):
    """네이버 카페 게시글 퍼블리셔 (Official API)."""

    platform = "naver_cafe"

    @property
    def default_club_id(self) -> str:
        return os.getenv("NAVER_CAFE_CLUB_ID", "")

    @property
    def default_menu_id(self) -> str:
        return os.getenv("NAVER_CAFE_MENU_ID", "")

    async def publish(self, content: PostContent) -> PublishResult:
        club_id = content.extra.get("club_id") or self.default_club_id
        menu_id = content.extra.get("menu_id") or self.default_menu_id

        if not club_id or not menu_id:
            return PublishResult(
                success=False,
                platform=self.platform,
                message=(
                    "club_id와 menu_id가 필요합니다. "
                    "환경변수(NAVER_CAFE_CLUB_ID, NAVER_CAFE_MENU_ID) 또는 "
                    "extra에 지정하세요."
                ),
            )

        token = await self._get_token()

        form_data = {
            "title": content.title,
            "content": content.body,
        }
        if content.visibility == "public":
            form_data["openyn"] = "true"
        else:
            form_data["openyn"] = "false"

        headers = {"Authorization": f"Bearer {token}"}
        url = f"{NAVER_CAFE_API}/{club_id}/menu/{menu_id}/articles"

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, data=form_data)

            if resp.status_code == 200:
                data = resp.json()
                result_msg = data.get("message", {}).get("result", {})
                article_id = str(result_msg.get("articleId", ""))
                article_url = result_msg.get("articleUrl", "")
                logger.info("[NaverCafe] 글 발행 성공: %s", article_url)
                return PublishResult(
                    success=True,
                    platform=self.platform,
                    post_id=article_id,
                    post_url=article_url,
                    message="네이버 카페 글 발행 완료",
                    raw_response=data,
                )

            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}

            error_msg = data.get("message", resp.text)
            logger.error("[NaverCafe] 글 발행 실패 (%d): %s", resp.status_code, error_msg)
            return PublishResult(
                success=False,
                platform=self.platform,
                message=f"발행 실패 ({resp.status_code}): {error_msg}",
                raw_response=data,
            )

    async def delete(self, post_id: str) -> bool:
        # 네이버 카페 API는 삭제 엔드포인트를 제공하지 않음
        logger.warning("[NaverCafe] API를 통한 직접 삭제는 지원되지 않습니다.")
        return False
