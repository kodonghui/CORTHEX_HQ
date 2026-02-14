"""
네이버 뉴스 검색 Tool.

네이버 검색 API를 사용하여 최신 뉴스를 검색하고
LLM이 시장 영향과 핵심 내용을 분석합니다.

사용 방법:
  - action="search": 키워드로 뉴스 검색 (최신순/정확도순)
  - action="finance": 금융·경제 뉴스 검색 (키워드에 금융 필터 자동 추가)

필요 환경변수:
  - NAVER_CLIENT_ID: 네이버 개발자센터 (https://developers.naver.com)
  - NAVER_CLIENT_SECRET: 위와 동일
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.naver_news")

NAVER_NEWS_API = "https://openapi.naver.com/v1/search/news.json"


class NaverNewsTool(BaseTool):
    """네이버 뉴스 검색 및 분석 도구."""

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
        elif action == "finance":
            return await self._finance_search(kwargs)
        else:
            return f"알 수 없는 action: {action}. search 또는 finance를 사용하세요."

    # ── 뉴스 검색 ──

    async def _search(self, kwargs: dict[str, Any]) -> str:
        query = kwargs.get("query", "")
        if not query:
            return "검색어(query)를 입력해주세요."

        if not os.getenv("NAVER_CLIENT_ID"):
            return (
                "NAVER_CLIENT_ID가 설정되지 않았습니다.\n"
                "네이버 개발자센터(https://developers.naver.com)에서 "
                "애플리케이션을 등록하고 '검색' API를 활성화한 뒤,\n"
                "Client ID와 Secret을 .env에 추가하세요.\n"
                "예: NAVER_CLIENT_ID=your-client-id\n"
                "    NAVER_CLIENT_SECRET=your-client-secret"
            )

        display = min(int(kwargs.get("size", 10)), 100)
        sort = kwargs.get("sort", "date")  # date(최신순) / sim(정확도순)
        start = int(kwargs.get("page", 1))

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    NAVER_NEWS_API,
                    headers=self._headers,
                    params={
                        "query": query,
                        "display": str(display),
                        "start": str(start),
                        "sort": sort,
                    },
                    timeout=15,
                )
        except httpx.HTTPError as e:
            return f"네이버 뉴스 API 호출 실패: {e}"

        if resp.status_code == 401:
            return (
                "네이버 API 인증 실패 (401). "
                "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET이 올바른지 확인하세요."
            )

        if resp.status_code != 200:
            logger.error("[NaverNews] 검색 실패 (%d): %s", resp.status_code, resp.text)
            return f"네이버 API 오류 ({resp.status_code}): {resp.text[:200]}"

        data = resp.json()
        total = data.get("total", 0)
        items = data.get("items", [])

        if not items:
            return f"'{query}' 관련 뉴스가 없습니다."

        # 결과 포맷팅
        results = []
        for i, item in enumerate(items, 1):
            title = self._strip_html(item.get("title", ""))
            desc = self._strip_html(item.get("description", ""))
            pub_date = item.get("pubDate", "")[:16]
            link = item.get("link", "")

            results.append(
                f"[{i}] {title}\n"
                f"    요약: {desc}\n"
                f"    날짜: {pub_date}\n"
                f"    링크: {link}"
            )

        sort_label = "최신순" if sort == "date" else "정확도순"
        search_text = (
            f"검색어: '{query}' | 총 {total:,}건 중 {len(items)}건 표시\n"
            f"정렬: {sort_label}\n\n"
            + "\n\n".join(results)
        )

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 뉴스 분석 전문가입니다.\n"
                "뉴스 검색 결과를 분석하여 다음을 정리하세요:\n"
                "1. 핵심 뉴스 3개 선정 및 요약 (각 2~3줄)\n"
                "2. 전체적인 뉴스 흐름/트렌드\n"
                "3. 시장·사업에 미치는 영향 분석\n"
                "4. 주의해야 할 리스크 요인\n"
                "출처(언론사)를 명시하세요. 한국어로 답변하세요."
            ),
            user_prompt=search_text,
        )

        return f"## 네이버 뉴스 검색 결과\n\n{search_text}\n\n---\n\n## 분석\n\n{analysis}"

    # ── 금융 뉴스 검색 ──

    async def _finance_search(self, kwargs: dict[str, Any]) -> str:
        query = kwargs.get("query", "")
        if not query:
            return "검색어(query)를 입력해주세요. 예: '삼성전자', '금리 인상'"

        # 금융 키워드 자동 추가
        finance_keywords = ["주식", "주가", "금리", "환율", "시장", "투자", "실적"]
        has_finance = any(kw in query for kw in finance_keywords)
        if not has_finance:
            query = f"{query} 주가 OR 실적 OR 시장"

        kwargs["query"] = query
        kwargs["sort"] = "date"  # 금융 뉴스는 최신순이 중요
        return await self._search(kwargs)

    # ── 유틸 ──

    @staticmethod
    def _strip_html(text: str) -> str:
        """HTML 태그 및 특수 엔티티 제거."""
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&quot;", '"').replace("&amp;", "&")
        text = text.replace("&lt;", "<").replace("&gt;", ">")
        return text.strip()
