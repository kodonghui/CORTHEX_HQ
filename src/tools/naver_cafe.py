"""
네이버 카페 검색/읽기 Tool.

네이버 Open API를 사용하여 카페 글을 검색하고,
검색 결과를 LLM이 분석·요약합니다.

사용 방법:
  - action="search": 키워드로 카페 글 검색
  - action="read": 특정 카페 글 URL의 본문 크롤링 (공개 글만)

필요 환경변수:
  - NAVER_CLIENT_ID: 네이버 개발자 센터 Client ID
  - NAVER_CLIENT_SECRET: 네이버 개발자 센터 Client Secret
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from urllib.parse import quote

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.naver_cafe")

NAVER_SEARCH_API = "https://openapi.naver.com/v1/search"


class NaverCafeTool(BaseTool):
    """네이버 카페 검색 및 글 읽기 도구."""

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "X-Naver-Client-Id": os.getenv("NAVER_CLIENT_ID", ""),
            "X-Naver-Client-Secret": os.getenv("NAVER_CLIENT_SECRET", ""),
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "search")

        if action == "search":
            return await self._search(kwargs)
        elif action == "read":
            return await self._read_article(kwargs)
        else:
            return f"알 수 없는 action: {action}. search 또는 read를 사용하세요."

    # ── 카페 글 검색 ──

    async def _search(self, kwargs: dict[str, Any]) -> str:
        query = kwargs.get("query", "")
        if not query:
            return "검색어(query)를 입력해주세요."

        if not os.getenv("NAVER_CLIENT_ID"):
            return await self._fallback_search(query)

        display = min(int(kwargs.get("display", 10)), 100)
        sort = kwargs.get("sort", "sim")  # sim(정확도) / date(최신)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{NAVER_SEARCH_API}/cafearticle.json",
                headers=self._headers,
                params={
                    "query": query,
                    "display": str(display),
                    "sort": sort,
                },
            )

            if resp.status_code != 200:
                error_msg = resp.text
                logger.error("[NaverCafe] 검색 실패 (%d): %s", resp.status_code, error_msg)
                return f"네이버 API 오류 ({resp.status_code}): {error_msg}"

            data = resp.json()

        items = data.get("items", [])
        total = data.get("total", 0)

        if not items:
            return f"'{query}' 검색 결과가 없습니다."

        # 검색 결과를 정리
        results = []
        for i, item in enumerate(items, 1):
            title = self._strip_html(item.get("title", ""))
            desc = self._strip_html(item.get("description", ""))
            cafe_name = item.get("cafename", "")
            cafe_url = item.get("cafeurl", "")
            link = item.get("link", "")

            results.append(
                f"[{i}] {title}\n"
                f"    카페: {cafe_name} ({cafe_url})\n"
                f"    요약: {desc}\n"
                f"    링크: {link}"
            )

        search_text = (
            f"검색어: '{query}' | 총 {total:,}건 중 {len(items)}건 표시\n"
            f"정렬: {'정확도순' if sort == 'sim' else '최신순'}\n\n"
            + "\n\n".join(results)
        )

        # LLM으로 검색 결과 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 시장조사 리서치 어시스턴트입니다.\n"
                "네이버 카페 검색 결과를 분석하여 다음을 정리하세요:\n"
                "1. 핵심 트렌드/의견 요약 (3~5줄)\n"
                "2. 주요 키워드/토픽 분류\n"
                "3. 소비자 반응/분위기 분석 (긍정/부정/중립)\n"
                "4. 시장조사에 유용한 인사이트\n"
                "출처(카페명)를 명시하세요."
            ),
            user_prompt=search_text,
        )

        return f"## 네이버 카페 검색 결과\n\n{search_text}\n\n---\n\n## 분석\n\n{analysis}"

    # ── 카페 글 본문 읽기 (공개 글) ──

    async def _read_article(self, kwargs: dict[str, Any]) -> str:
        url = kwargs.get("url", "")
        if not url:
            return "읽을 글의 URL을 입력해주세요."

        async with httpx.AsyncClient(follow_redirects=True) as client:
            try:
                resp = await client.get(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                    },
                    timeout=15,
                )
            except httpx.HTTPError as e:
                return f"URL 접근 실패: {e}"

        if resp.status_code != 200:
            return f"페이지 접근 실패 (HTTP {resp.status_code}). 비공개 글이거나 로그인이 필요할 수 있습니다."

        html = resp.text

        # 본문 텍스트 추출 (간이 파서)
        body_text = self._extract_text_from_html(html)

        if len(body_text) < 50:
            return (
                "본문을 추출하지 못했습니다. "
                "비공개 글이거나 로그인이 필요한 카페일 수 있습니다.\n"
                "검색 API(action=search)를 사용하면 공개 요약을 볼 수 있습니다."
            )

        # 너무 긴 본문은 자르기
        if len(body_text) > 5000:
            body_text = body_text[:5000] + "\n\n... (이하 생략)"

        # LLM으로 본문 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 시장조사 리서치 어시스턴트입니다.\n"
                "네이버 카페 글을 읽고 다음을 정리하세요:\n"
                "1. 글의 핵심 내용 요약 (3~5줄)\n"
                "2. 주요 키워드\n"
                "3. 시장조사에 유용한 포인트\n"
                "4. 글쓴이의 의견/감정 톤 분석"
            ),
            user_prompt=f"URL: {url}\n\n본문:\n{body_text}",
        )

        return f"## 카페 글 읽기\n\nURL: {url}\n\n### 본문\n{body_text}\n\n---\n\n### 분석\n{analysis}"

    # ── API 키 없을 때 LLM 기반 폴백 ──

    async def _fallback_search(self, query: str) -> str:
        return await self._llm_call(
            system_prompt=(
                "당신은 네이버 카페 리서치 어시스턴트입니다.\n"
                "네이버 API 키가 설정되지 않았습니다.\n"
                "주어진 주제에 대해 네이버 카페에서 볼 수 있는 일반적인\n"
                "소비자 의견, 트렌드, 반응을 지식 기반으로 추정하세요.\n"
                "반드시 '추정 데이터'임을 명시하세요.\n"
                "API 키 설정 안내: NAVER_CLIENT_ID, NAVER_CLIENT_SECRET을 .env에 추가하세요."
            ),
            user_prompt=f"네이버 카페에서 '{query}' 관련 소비자 반응 조사",
        )

    # ── 유틸 ──

    @staticmethod
    def _strip_html(text: str) -> str:
        """HTML 태그 제거."""
        return re.sub(r"<[^>]+>", "", text).strip()

    @staticmethod
    def _extract_text_from_html(html: str) -> str:
        """HTML에서 본문 텍스트를 간이 추출."""
        # script/style 제거
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)

        # 네이버 카페 본문 영역 추출 시도
        patterns = [
            r'class="se-main-container"[^>]*>(.*?)</div>',
            r'class="ContentRenderer"[^>]*>(.*?)</div>',
            r'id="postViewArea"[^>]*>(.*?)</div>',
            r'class="article_viewer"[^>]*>(.*?)</div>',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                html = match.group(1)
                break

        # 태그 제거 + 공백 정리
        text = re.sub(r"<br\s*/?>", "\n", html)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
