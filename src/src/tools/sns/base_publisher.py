"""
SNS 퍼블리셔 베이스 클래스.

모든 플랫폼 퍼블리셔가 상속받는 공통 인터페이스.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from src.tools.sns.oauth_manager import OAuthManager

logger = logging.getLogger("corthex.sns.publisher")


@dataclass
class PublishResult:
    """퍼블리싱 결과."""

    success: bool
    platform: str
    post_id: str = ""
    post_url: str = ""
    message: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass
class PostContent:
    """플랫폼에 올릴 콘텐츠 데이터."""

    title: str = ""
    body: str = ""
    tags: list[str] = field(default_factory=list)
    category: str = ""
    visibility: str = "public"  # public, private, draft
    media_urls: list[str] = field(default_factory=list)
    thumbnail_url: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class BasePublisher(ABC):
    """SNS 퍼블리셔 추상 베이스 클래스."""

    platform: str = ""

    def __init__(self, oauth: OAuthManager) -> None:
        self.oauth = oauth

    async def _get_token(self) -> str:
        return await self.oauth.get_valid_access_token(self.platform)

    @abstractmethod
    async def publish(self, content: PostContent) -> PublishResult:
        """콘텐츠를 해당 플랫폼에 게시."""
        ...

    @abstractmethod
    async def delete(self, post_id: str) -> bool:
        """게시물 삭제."""
        ...

    async def check_connection(self) -> bool:
        """플랫폼 연결 상태 확인."""
        return self.oauth.has_valid_token(self.platform)
