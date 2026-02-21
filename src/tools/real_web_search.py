"""실시간 웹 검색 도구 — Serper.dev 우선, SerpAPI 폴백.

Serper.dev: 월 2,500회 무료, 실제 구글 결과 (SERPER_API_KEY)
SerpAPI:    월 100회 무료, 실제 구글 결과 (SERPAPI_KEY) — 폴백용
"""
from __future__ import annotations

import logging
import os
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.real_web_search")


def _get_httpx():
    """httpx 지연 임포트."""
    try:
        import httpx
        return httpx
    except ImportError:
        return None


class RealWebSearchTool(BaseTool):
    """Serper.dev + SerpAPI 이중 백엔드 실시간 웹 검색 도구."""

    SERPER_BASE = "https://google.serper.dev"
    SERPAPI_URL = "https://serpapi.com/search.json"

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "search")
        if action == "search":
            return await self._search(kwargs)
        elif action == "news":
            return await self._news(kwargs)
        elif action == "image":
            return await self._image(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능한 action: search(웹 검색), news(뉴스 검색), image(이미지 검색)"
            )

    # ── 백엔드 선택 ──

    @staticmethod
    def _get_serper_key() -> str:
        return os.getenv("SERPER_API_KEY", "")

    @staticmethod
    def _get_serpapi_key() -> str:
        return os.getenv("SERPAPI_KEY", "")

    def _has_any_key(self) -> bool:
        return bool(self._get_serper_key() or self._get_serpapi_key())

    # ── Serper.dev API 호출 ──

    async def _call_serper(self, endpoint: str, payload: dict) -> dict | None:
        """Serper.dev POST 호출. 키 없거나 실패하면 None 반환."""
        httpx = _get_httpx()
        if httpx is None:
            return None

        api_key = self._get_serper_key()
        if not api_key:
            return None

        payload.setdefault("gl", "kr")
        payload.setdefault("hl", "ko")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.SERPER_BASE}/{endpoint}",
                    headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning("Serper.dev 호출 실패 (SerpAPI 폴백): %s", e)
            return None

    # ── SerpAPI 폴백 호출 ──

    async def _call_serpapi(self, params: dict) -> dict | None:
        """SerpAPI GET 호출. 키 없거나 실패하면 None 반환."""
        httpx = _get_httpx()
        if httpx is None:
            return None

        api_key = self._get_serpapi_key()
        if not api_key:
            return None

        params["api_key"] = api_key
        params.setdefault("hl", "ko")
        params.setdefault("gl", "kr")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(self.SERPAPI_URL, params=params)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error("SerpAPI 호출 실패: %s", e)
            return None

    # ── 웹 검색 ──

    async def _search(self, kwargs: dict) -> str:
        query = kwargs.get("query", "")
        if not query:
            return "검색어(query)를 입력해주세요."

        num = int(kwargs.get("num", 10))

        # 1차: Serper.dev
        data = await self._call_serper("search", {"q": query, "num": num})
        if data and "organic" in data:
            results = data["organic"][:num]
            lines = [f"## 웹 검색 결과: {query}\n"]
            for i, r in enumerate(results, 1):
                lines.append(f"### {i}. {r.get('title', '제목 없음')}")
                lines.append(f"- 링크: {r.get('link', '')}")
                lines.append(f"- 요약: {r.get('snippet', '')}\n")
            formatted = "\n".join(lines)
            logger.info("[Serper.dev] 검색 성공: %s (%d건)", query, len(results))
        else:
            # 2차: SerpAPI 폴백
            data = await self._call_serpapi({"engine": "google", "q": query, "num": num})
            if data is None or "error" in (data or {}):
                if not self._has_any_key():
                    return (
                        "웹 검색 API 키가 설정되지 않았습니다.\n"
                        "SERPER_API_KEY 또는 SERPAPI_KEY를 환경변수에 추가하세요."
                    )
                return f"웹 검색 실패: {(data or {}).get('error', '알 수 없는 오류')}"

            results = data.get("organic_results", [])[:num]
            if not results:
                return f"'{query}' 검색 결과가 없습니다."

            lines = [f"## 웹 검색 결과: {query}\n"]
            for i, r in enumerate(results, 1):
                lines.append(f"### {i}. {r.get('title', '제목 없음')}")
                lines.append(f"- 링크: {r.get('link', '')}")
                lines.append(f"- 요약: {r.get('snippet', '')}\n")
            formatted = "\n".join(lines)
            logger.info("[SerpAPI 폴백] 검색 성공: %s (%d건)", query, len(results))

        # LLM 종합 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 검색 결과를 분석하는 리서치 전문가입니다. "
                "검색 결과를 종합하여 핵심 정보를 한국어로 요약하세요. "
                "출처를 명시하고, 사실과 의견을 구분하세요."
            ),
            user_prompt=f"검색어: {query}\n\n검색 결과:\n{formatted}",
        )

        return f"{formatted}\n---\n\n## 종합 분석\n\n{analysis}"

    # ── 뉴스 검색 ──

    async def _news(self, kwargs: dict) -> str:
        query = kwargs.get("query", "")
        if not query:
            return "검색어(query)를 입력해주세요."

        num = int(kwargs.get("num", 10))

        # 1차: Serper.dev /news
        data = await self._call_serper("news", {"q": query, "num": num})
        if data and "news" in data:
            results = data["news"][:num]
            lines = [f"## 뉴스 검색 결과: {query}\n"]
            for i, r in enumerate(results, 1):
                lines.append(f"### {i}. {r.get('title', '제목 없음')}")
                lines.append(f"- 출처: {r.get('source', '')} | 날짜: {r.get('date', '')}")
                lines.append(f"- 링크: {r.get('link', '')}")
                lines.append(f"- 내용: {r.get('snippet', '')}\n")
            formatted = "\n".join(lines)
            logger.info("[Serper.dev] 뉴스 검색 성공: %s (%d건)", query, len(results))
        else:
            # 2차: SerpAPI 폴백
            data = await self._call_serpapi({"engine": "google", "q": query, "tbm": "nws", "num": num})
            if data is None or "error" in (data or {}):
                if not self._has_any_key():
                    return "웹 검색 API 키가 설정되지 않았습니다."
                return f"뉴스 검색 실패: {(data or {}).get('error', '알 수 없는 오류')}"

            results = data.get("news_results", [])[:num]
            if not results:
                return f"'{query}' 관련 뉴스가 없습니다."

            lines = [f"## 뉴스 검색 결과: {query}\n"]
            for i, r in enumerate(results, 1):
                lines.append(f"### {i}. {r.get('title', '제목 없음')}")
                lines.append(f"- 출처: {r.get('source', '')} | 날짜: {r.get('date', '')}")
                lines.append(f"- 링크: {r.get('link', '')}")
                lines.append(f"- 내용: {r.get('snippet', '')}\n")
            formatted = "\n".join(lines)
            logger.info("[SerpAPI 폴백] 뉴스 검색 성공: %s (%d건)", query, len(results))

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 뉴스 분석 전문가입니다. "
                "뉴스 검색 결과를 종합하여 핵심 트렌드와 시사점을 한국어로 분석하세요."
            ),
            user_prompt=f"검색어: {query}\n\n뉴스 결과:\n{formatted}",
        )

        return f"{formatted}\n---\n\n## 뉴스 분석\n\n{analysis}"

    # ── 이미지 검색 ──

    async def _image(self, kwargs: dict) -> str:
        query = kwargs.get("query", "")
        if not query:
            return "검색어(query)를 입력해주세요."

        num = int(kwargs.get("num", 5))

        # 1차: Serper.dev /images
        data = await self._call_serper("images", {"q": query, "num": num})
        if data and "images" in data:
            results = data["images"][:num]
            lines = [f"## 이미지 검색 결과: {query}\n"]
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. **{r.get('title', '제목 없음')}**")
                lines.append(f"   - 이미지 URL: {r.get('imageUrl', '')}")
                lines.append(f"   - 출처: {r.get('link', '')}\n")
            return "\n".join(lines)

        # 2차: SerpAPI 폴백
        data = await self._call_serpapi({"engine": "google", "q": query, "tbm": "isch", "num": num})
        if data is None or "error" in (data or {}):
            if not self._has_any_key():
                return "웹 검색 API 키가 설정되지 않았습니다."
            return f"이미지 검색 실패: {(data or {}).get('error', '알 수 없는 오류')}"

        results = data.get("images_results", [])[:num]
        if not results:
            return f"'{query}' 관련 이미지가 없습니다."

        lines = [f"## 이미지 검색 결과: {query}\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{r.get('title', '제목 없음')}**")
            lines.append(f"   - 이미지 URL: {r.get('original', '')}")
            lines.append(f"   - 출처: {r.get('source', '')}\n")
        return "\n".join(lines)
