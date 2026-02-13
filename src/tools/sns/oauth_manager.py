"""
OAuth 토큰 관리자.

각 SNS 플랫폼의 OAuth 토큰을 안전하게 저장·갱신·조회합니다.
- 토큰 암호화 저장 (JSON 파일 기반)
- 자동 만료 감지 및 refresh_token으로 갱신
- 플랫폼별 OAuth 인증 URL 생성
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("corthex.sns.oauth")

# 토큰 저장 경로
TOKEN_STORE_PATH = Path(os.getenv(
    "SNS_TOKEN_STORE",
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "sns_tokens.json",
))


class OAuthToken:
    """단일 플랫폼의 OAuth 토큰 데이터."""

    def __init__(
        self,
        platform: str,
        access_token: str,
        refresh_token: str = "",
        expires_at: float = 0,
        token_type: str = "Bearer",
        scope: str = "",
    ) -> None:
        self.platform = platform
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.token_type = token_type
        self.scope = scope

    @property
    def is_expired(self) -> bool:
        if self.expires_at == 0:
            return False
        return time.time() >= self.expires_at - 60  # 1분 여유

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "token_type": self.token_type,
            "scope": self.scope,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OAuthToken:
        return cls(**data)


# ── 플랫폼별 OAuth 설정 ──

PLATFORM_CONFIG: dict[str, dict[str, str]] = {
    "tistory": {
        "auth_url": "https://www.tistory.com/oauth/authorize",
        "token_url": "https://www.tistory.com/oauth/access_token",
        "env_client_id": "TISTORY_CLIENT_ID",
        "env_client_secret": "TISTORY_CLIENT_SECRET",
        "env_redirect_uri": "TISTORY_REDIRECT_URI",
    },
    "youtube": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "env_client_id": "GOOGLE_CLIENT_ID",
        "env_client_secret": "GOOGLE_CLIENT_SECRET",
        "env_redirect_uri": "GOOGLE_REDIRECT_URI",
        "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube",
    },
    "instagram": {
        "auth_url": "https://api.instagram.com/oauth/authorize",
        "token_url": "https://api.instagram.com/oauth/access_token",
        "long_lived_url": "https://graph.instagram.com/access_token",
        "refresh_url": "https://graph.instagram.com/refresh_access_token",
        "env_client_id": "INSTAGRAM_APP_ID",
        "env_client_secret": "INSTAGRAM_APP_SECRET",
        "env_redirect_uri": "INSTAGRAM_REDIRECT_URI",
        "scope": "instagram_basic,instagram_content_publish",
    },
    "linkedin": {
        "auth_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "env_client_id": "LINKEDIN_CLIENT_ID",
        "env_client_secret": "LINKEDIN_CLIENT_SECRET",
        "env_redirect_uri": "LINKEDIN_REDIRECT_URI",
        "scope": "openid profile w_member_social",
    },
    "naver_cafe": {
        "auth_url": "https://nid.naver.com/oauth2.0/authorize",
        "token_url": "https://nid.naver.com/oauth2.0/token",
        "env_client_id": "NAVER_CLIENT_ID",
        "env_client_secret": "NAVER_CLIENT_SECRET",
        "env_redirect_uri": "NAVER_REDIRECT_URI",
        "scope": "cafe",
    },
}


class OAuthManager:
    """모든 플랫폼의 OAuth 토큰을 중앙 관리."""

    def __init__(self) -> None:
        self._tokens: dict[str, OAuthToken] = {}
        self._load()

    # ── 저장/로드 ──

    def _load(self) -> None:
        if TOKEN_STORE_PATH.exists():
            try:
                raw = json.loads(TOKEN_STORE_PATH.read_text(encoding="utf-8"))
                for platform, data in raw.items():
                    self._tokens[platform] = OAuthToken.from_dict(data)
                logger.info("토큰 스토어 로드: %d개 플랫폼", len(self._tokens))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("토큰 스토어 파싱 실패: %s", e)

    def _save(self) -> None:
        TOKEN_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {k: v.to_dict() for k, v in self._tokens.items()}
        TOKEN_STORE_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.debug("토큰 스토어 저장 완료")

    # ── 토큰 조회/저장 ──

    def get_token(self, platform: str) -> OAuthToken | None:
        return self._tokens.get(platform)

    def set_token(self, token: OAuthToken) -> None:
        self._tokens[token.platform] = token
        self._save()
        logger.info("[%s] 토큰 저장 완료", token.platform)

    def has_valid_token(self, platform: str) -> bool:
        token = self.get_token(platform)
        return token is not None and not token.is_expired

    # ── OAuth 인증 URL 생성 ──

    def get_auth_url(self, platform: str) -> str:
        cfg = PLATFORM_CONFIG.get(platform)
        if not cfg:
            raise ValueError(f"미지원 플랫폼: {platform}")

        client_id = os.getenv(cfg["env_client_id"], "")
        redirect_uri = os.getenv(cfg["env_redirect_uri"], "")

        if not client_id:
            raise ValueError(f"{cfg['env_client_id']} 환경변수가 설정되지 않았습니다.")

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
        }
        if "scope" in cfg:
            params["scope"] = cfg["scope"]

        # Tistory는 response_type이 다름
        if platform == "tistory":
            params["response_type"] = "code"

        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{cfg['auth_url']}?{query}"

    # ── 인증 코드 → 토큰 교환 ──

    async def exchange_code(self, platform: str, code: str) -> OAuthToken:
        cfg = PLATFORM_CONFIG.get(platform)
        if not cfg:
            raise ValueError(f"미지원 플랫폼: {platform}")

        client_id = os.getenv(cfg["env_client_id"], "")
        client_secret = os.getenv(cfg["env_client_secret"], "")
        redirect_uri = os.getenv(cfg["env_redirect_uri"], "")

        payload = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(cfg["token_url"], data=payload)

            if platform == "tistory":
                # Tistory는 key=value 형태로 반환
                if "access_token" in resp.text:
                    parts = dict(p.split("=") for p in resp.text.split("&"))
                    token = OAuthToken(
                        platform="tistory",
                        access_token=parts["access_token"],
                    )
                else:
                    raise RuntimeError(f"Tistory 토큰 교환 실패: {resp.text}")
            else:
                data = resp.json()
                if "error" in data:
                    raise RuntimeError(f"{platform} 토큰 교환 실패: {data}")

                expires_in = data.get("expires_in", 0)
                token = OAuthToken(
                    platform=platform,
                    access_token=data["access_token"],
                    refresh_token=data.get("refresh_token", ""),
                    expires_at=time.time() + expires_in if expires_in else 0,
                    token_type=data.get("token_type", "Bearer"),
                    scope=data.get("scope", ""),
                )

        self.set_token(token)
        return token

    # ── 토큰 자동 갱신 ──

    async def refresh_if_needed(self, platform: str) -> OAuthToken | None:
        token = self.get_token(platform)
        if not token:
            return None
        if not token.is_expired:
            return token

        if not token.refresh_token:
            logger.warning("[%s] 토큰 만료됨, refresh_token 없음 → 재인증 필요", platform)
            return None

        cfg = PLATFORM_CONFIG.get(platform)
        if not cfg:
            return None

        client_id = os.getenv(cfg["env_client_id"], "")
        client_secret = os.getenv(cfg["env_client_secret"], "")

        payload = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": token.refresh_token,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(cfg["token_url"], data=payload)
            data = resp.json()

            if "error" in data:
                logger.error("[%s] 토큰 갱신 실패: %s", platform, data)
                return None

            expires_in = data.get("expires_in", 0)
            new_token = OAuthToken(
                platform=platform,
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token", token.refresh_token),
                expires_at=time.time() + expires_in if expires_in else 0,
                token_type=data.get("token_type", "Bearer"),
                scope=data.get("scope", token.scope),
            )

        self.set_token(new_token)
        logger.info("[%s] 토큰 자동 갱신 완료", platform)
        return new_token

    # ── 유효한 액세스 토큰 가져오기 ──

    async def get_valid_access_token(self, platform: str) -> str:
        token = await self.refresh_if_needed(platform)
        if not token:
            raise RuntimeError(
                f"[{platform}] 유효한 토큰 없음. "
                f"인증 URL: {self.get_auth_url(platform)}"
            )
        return token.access_token

    # ── 상태 조회 ──

    def status(self) -> list[dict[str, Any]]:
        result = []
        for platform in PLATFORM_CONFIG:
            token = self._tokens.get(platform)
            result.append({
                "platform": platform,
                "connected": token is not None,
                "expired": token.is_expired if token else True,
                "has_refresh": bool(token.refresh_token) if token else False,
            })
        return result
