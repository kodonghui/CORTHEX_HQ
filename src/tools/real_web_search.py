"""실시간 웹 검색 도구 — SerpAPI를 통한 실제 구글 검색."""
from __future__ import annotations

import json
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
    """SerpAPI를 사용한 실시간 구글 웹 검색 도구."""

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

    # ── 내부 헬퍼 ──

    @staticmethod
    def _get_api_key() -> str:
        return os.getenv("SERPAPI_KEY", "")

    @staticmethod
    def _key_msg() -> str:
        return (
            "SERPAPI_KEY 환경변수가 설정되지 않았습니다.\n"
            "https://serpapi.com 에서 API 키를 발급받은 뒤 .env에 추가하세요.\n"
            "예: SERPAPI_KEY=your_api_key_here"
        )

    async def _call_serpapi(self, params: dict) -> dict:
        """SerpAPI HTTP 호출."""
        httpx = _get_httpx()
        if httpx is None:
            return {"error": "httpx 라이브러리가 설치되지 않았습니다. pip install httpx"}

        api_key = self._get_api_key()
        if not api_key:
            return {"error": self._key_msg()}

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
            return {"error": f"SerpAPI 호출 실패: {e}"}

    async def _search(self, kwargs: dict) -> str:
        """일반 웹 검색."""
        query = kwargs.get("query", "")
        if not query:
            return "검색어(query)를 입력해주세요."

        num = int(kwargs.get("num", 10))
        data = await self._call_serpapi({"engine": "google", "q": query, "num": num})

        if "error" in data:
            return data["error"]

        results = data.get("organic_results", [])
        if not results:
            return f"'{query}' 검색 결과가 없습니다."

        lines: list[str] = [f"## 🔍 웹 검색 결과: {query}\n"]
        for i, r in enumerate(results[:num], 1):
            title = r.get("title", "제목 없음")
            link = r.get("link", "")
            snippet = r.get("snippet", "")
            lines.append(f"### {i}. {title}")
            lines.append(f"- 링크: {link}")
            lines.append(f"- 요약: {snippet}\n")

        formatted = "\n".join(lines)

        # LLM으로 검색 결과 종합 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 검색 결과를 분석하는 리서치 전문가입니다. "
                "검색 결과를 종합하여 핵심 정보를 한국어로 요약하세요. "
                "출처를 명시하고, 사실과 의견을 구분하세요."
            ),
            user_prompt=f"검색어: {query}\n\n검색 결과:\n{formatted}",
        )

        return f"{formatted}\n---\n\n## 📊 종합 분석\n\n{analysis}"

    async def _news(self, kwargs: dict) -> str:
        """뉴스 검색."""
        query = kwargs.get("query", "")
        if not query:
            return "검색어(query)를 입력해주세요."

        num = int(kwargs.get("num", 10))
        data = await self._call_serpapi({"engine": "google", "q": query, "tbm": "nws", "num": num})

        if "error" in data:
            return data["error"]

        results = data.get("news_results", [])
        if not results:
            return f"'{query}' 관련 뉴스가 없습니다."

        lines: list[str] = [f"## 📰 뉴스 검색 결과: {query}\n"]
        for i, r in enumerate(results[:num], 1):
            title = r.get("title", "제목 없음")
            link = r.get("link", "")
            source = r.get("source", "")
            date = r.get("date", "")
            snippet = r.get("snippet", "")
            lines.append(f"### {i}. {title}")
            lines.append(f"- 출처: {source} | 날짜: {date}")
            lines.append(f"- 링크: {link}")
            lines.append(f"- 내용: {snippet}\n")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 뉴스 분석 전문가입니다. "
                "뉴스 검색 결과를 종합하여 핵심 트렌드와 시사점을 한국어로 분석하세요."
            ),
            user_prompt=f"검색어: {query}\n\n뉴스 결과:\n{formatted}",
        )

        return f"{formatted}\n---\n\n## 📊 뉴스 분석\n\n{analysis}"

    async def _image(self, kwargs: dict) -> str:
        """이미지 검색."""
        query = kwargs.get("query", "")
        if not query:
            return "검색어(query)를 입력해주세요."

        num = int(kwargs.get("num", 5))
        data = await self._call_serpapi({"engine": "google", "q": query, "tbm": "isch", "num": num})

        if "error" in data:
            return data["error"]

        results = data.get("images_results", [])
        if not results:
            return f"'{query}' 관련 이미지가 없습니다."

        lines: list[str] = [f"## 🖼️ 이미지 검색 결과: {query}\n"]
        for i, r in enumerate(results[:num], 1):
            title = r.get("title", "제목 없음")
            original = r.get("original", "")
            source = r.get("source", "")
            lines.append(f"{i}. **{title}**")
            lines.append(f"   - 이미지 URL: {original}")
            lines.append(f"   - 출처: {source}\n")

        return "\n".join(lines)
