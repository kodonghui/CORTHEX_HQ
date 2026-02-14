"""
네이버 플레이스 리뷰 수집기 Tool.

네이버 플레이스(지도)에서 매장/학원 리뷰를 수집하고 분석합니다.
검색, 리뷰 수집, 분석 기능을 제공합니다.

사용 방법:
  - action="search": 네이버 플레이스에서 장소 검색
  - action="reviews": 특정 장소의 리뷰 수집
  - action="analyze": 수집된 리뷰 분석

필요 환경변수: 없음
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import Counter
from typing import Any

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.naver_place_scraper")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# 네이버 플레이스 API (비공식)
NAVER_SEARCH_API = "https://map.naver.com/v5/api/search"
NAVER_REVIEW_API = "https://map.naver.com/v5/api/sites/summary/{place_id}/review"


class NaverPlaceScraperTool(BaseTool):
    """네이버 플레이스 리뷰 수집 및 분석 도구."""

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": USER_AGENT,
            "Referer": "https://map.naver.com/",
            "Accept": "application/json",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "search")

        if action == "search":
            return await self._search_places(kwargs)
        elif action == "reviews":
            return await self._get_reviews(kwargs)
        elif action == "analyze":
            return await self._analyze_reviews(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "search, reviews, analyze 중 하나를 사용하세요."
            )

    # ── 장소 검색 ──

    async def _search_places(self, kwargs: dict[str, Any]) -> str:
        query = kwargs.get("query", "").strip()
        if not query:
            return "검색어(query)를 입력해주세요. 예: query='LEET 학원 서울'"

        count = min(int(kwargs.get("count", 10)), 30)

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(
                    NAVER_SEARCH_API,
                    params={"query": query, "type": "all", "lang": "ko"},
                    headers=self._headers,
                    timeout=15,
                )
        except httpx.HTTPError as e:
            logger.error("네이버 플레이스 검색 실패: %s", e)
            return f"검색 실패: {e}"

        if resp.status_code != 200:
            return (
                f"네이버 플레이스 API 응답 오류 (HTTP {resp.status_code}).\n"
                "네이버 API 정책 변경으로 접근이 제한되었을 수 있습니다."
            )

        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            return "응답 파싱 실패. 네이버 API 형식이 변경되었을 수 있습니다."

        # 결과 파싱 (네이버 플레이스 API 응답 구조에 따라 유연하게)
        places = []
        result_section = data.get("result", {})
        place_list = result_section.get("place", {}).get("list", [])

        if not place_list:
            # 다른 구조 시도
            place_list = data.get("place", {}).get("list", []) if isinstance(data.get("place"), dict) else []

        for place in place_list[:count]:
            place_id = place.get("id", "")
            name = place.get("name", "")
            category = place.get("category", "")
            address = place.get("address", place.get("roadAddress", ""))
            tel = place.get("tel", "")
            review_count = place.get("reviewCount", place.get("visitorReviewCount", 0))
            rating = place.get("rating", place.get("visitorReviewScore", ""))

            places.append({
                "id": place_id,
                "name": name,
                "category": category,
                "address": address,
                "tel": tel,
                "review_count": review_count,
                "rating": rating,
            })

        if not places:
            return (
                f"'{query}' 검색 결과가 없습니다.\n"
                "검색어를 변경하거나 네이버 지도에서 직접 검색해보세요."
            )

        lines = []
        for i, p in enumerate(places, 1):
            lines.append(
                f"**{i}. {p['name']}** (ID: {p['id']})\n"
                f"   카테고리: {p['category']}\n"
                f"   주소: {p['address']}\n"
                f"   전화: {p['tel']}\n"
                f"   리뷰: {p['review_count']}건 | 평점: {p['rating']}"
            )

        return (
            f"## 네이버 플레이스 검색 결과: '{query}'\n\n"
            f"총 {len(places)}개 장소\n\n"
            + "\n\n".join(lines)
            + "\n\n---\n리뷰를 보려면 action='reviews', place_id='ID번호'를 사용하세요."
        )

    # ── 리뷰 수집 ──

    async def _get_reviews(self, kwargs: dict[str, Any]) -> str:
        place_id = kwargs.get("place_id", "").strip()
        if not place_id:
            return (
                "장소 ID(place_id)를 입력해주세요.\n"
                "action='search'로 먼저 검색하여 ID를 확인하세요."
            )

        count = min(int(kwargs.get("count", 100)), 300)

        review_url = NAVER_REVIEW_API.format(place_id=place_id)

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(
                    review_url,
                    headers=self._headers,
                    timeout=15,
                )
        except httpx.HTTPError as e:
            return f"리뷰 조회 실패: {e}"

        if resp.status_code != 200:
            return (
                f"리뷰 API 응답 오류 (HTTP {resp.status_code}).\n"
                "place_id가 올바른지 확인하세요."
            )

        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            return "응답 파싱 실패."

        # 리뷰 데이터 파싱
        reviews = []
        review_list = data.get("reviews", data.get("list", []))
        if isinstance(data.get("result"), dict):
            review_list = data["result"].get("reviews", review_list)

        for review in review_list[:count]:
            text = review.get("body", review.get("content", ""))
            rating = review.get("rating", review.get("score", 0))
            date = review.get("date", review.get("created", ""))[:10]
            visit_purpose = review.get("visitPurpose", "")
            keywords = review.get("keywords", [])

            reviews.append({
                "text": text[:300],
                "rating": rating,
                "date": date,
                "visit_purpose": visit_purpose,
                "keywords": keywords if isinstance(keywords, list) else [],
            })

        if not reviews:
            return (
                f"place_id '{place_id}'의 리뷰를 찾을 수 없습니다.\n"
                "네이버 플레이스 API 구조가 변경되었을 수 있습니다."
            )

        # 별점 분포
        ratings = [r["rating"] for r in reviews if r["rating"]]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0
        dist = Counter(ratings)

        # 리뷰 표시
        review_lines = []
        for i, r in enumerate(reviews[:20], 1):
            kw_str = ", ".join(r["keywords"][:5]) if r["keywords"] else ""
            review_lines.append(
                f"[{i}] ★{r['rating']} | {r['date']}\n"
                f"    {r['text']}\n"
                f"    키워드: {kw_str}" if kw_str else
                f"[{i}] ★{r['rating']} | {r['date']}\n"
                f"    {r['text']}"
            )

        dist_text = " | ".join(
            f"{star}점: {dist.get(star, 0)}건"
            for star in range(5, 0, -1)
        )

        return (
            f"## 네이버 플레이스 리뷰\n\n"
            f"- **장소 ID**: {place_id}\n"
            f"- **수집 건수**: {len(reviews)}건\n"
            f"- **평균 별점**: {avg_rating:.1f}점\n"
            f"- **별점 분포**: {dist_text}\n\n"
            f"### 리뷰 목록 (상위 20건)\n\n"
            + "\n\n".join(review_lines)
        )

    # ── 리뷰 분석 ──

    async def _analyze_reviews(self, kwargs: dict[str, Any]) -> str:
        place_id = kwargs.get("place_id", "").strip()
        if not place_id:
            return "장소 ID(place_id)를 입력해주세요."

        # 리뷰 수집
        review_data = await self._get_reviews({
            "place_id": place_id,
            "count": 200,
        })

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 고객 리뷰 분석 전문가입니다.\n"
                "네이버 플레이스 리뷰를 분석하여 다음을 정리하세요:\n"
                "1. 고객 만족 요인 TOP 5 (구체적 근거 포함)\n"
                "2. 고객 불만 요인 TOP 5 (구체적 근거 포함)\n"
                "3. 자주 언급되는 긍정 키워드\n"
                "4. 자주 언급되는 부정 키워드\n"
                "5. 시간별 별점 추이 (개선/악화 방향)\n"
                "6. 경쟁 우위 포인트 (다른 곳과 차별화되는 강점)\n"
                "7. 개선 우선순위 제안\n"
                "한국어로 간결하게 보고하세요."
            ),
            user_prompt=review_data,
        )

        return (
            f"## 네이버 플레이스 리뷰 분석 보고서\n\n"
            f"장소 ID: {place_id}\n\n"
            f"---\n\n{analysis}"
        )
