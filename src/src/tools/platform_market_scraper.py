"""
크몽/탈잉/클래스101 시장 조사 Tool.

플랫폼 마켓플레이스에서 특정 분야 서비스의
가격, 리뷰, 판매량 등을 수집하여 시장 분석합니다.

사용 방법:
  - action="search": 플랫폼에서 서비스 검색
  - action="analyze": 수집 결과 시장 분석
  - action="price_range": 가격대 분포 분석

필요 환경변수: 없음
의존 라이브러리: httpx, beautifulsoup4
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.platform_market_scraper")

# ── 크롤링 공통 헤더 ──
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


class PlatformMarketScraperTool(BaseTool):
    """크몽/탈잉/클래스101 플랫폼 시장 조사 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "search")

        if action == "search":
            return await self._search(kwargs)
        elif action == "analyze":
            return await self._analyze(kwargs)
        elif action == "price_range":
            return await self._price_range(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "search, analyze, price_range 중 하나를 사용하세요."
            )

    # ── 검색 ──

    async def _search(self, kwargs: dict[str, Any]) -> str:
        """플랫폼에서 서비스 검색."""
        platform = kwargs.get("platform", "all")
        query = kwargs.get("query", "")
        count = int(kwargs.get("count", 20))

        if not query:
            return "검색어(query)를 입력해주세요. 예: query='LEET', query='법학'"

        results: dict[str, list[dict]] = {}

        if platform in ("kmong", "all"):
            results["크몽"] = await self._scrape_kmong(query, count)
        if platform in ("taling", "all"):
            results["탈잉"] = await self._scrape_taling(query, count)
            await asyncio.sleep(1.5)  # 요청 간 딜레이
        if platform in ("class101", "all"):
            results["클래스101"] = await self._scrape_class101(query, count)

        if not any(results.values()):
            return f"'{query}' 관련 서비스를 찾을 수 없습니다."

        lines = [f"## 플랫폼 시장 검색 결과: '{query}'\n"]
        total_count = 0
        for pname, items in results.items():
            lines.append(f"### {pname} ({len(items)}건)")
            for i, item in enumerate(items, 1):
                price_str = f"{item.get('price', '가격 미정'):,}" if isinstance(item.get('price'), (int, float)) else item.get('price', '가격 미정')
                lines.append(
                    f"  [{i}] {item.get('title', '제목 없음')}\n"
                    f"      가격: {price_str}원 | "
                    f"별점: {item.get('rating', '-')} | "
                    f"리뷰/수강생: {item.get('reviews', '-')}"
                )
            total_count += len(items)
            lines.append("")

        lines.append(f"---\n**총 {total_count}건** 수집 완료")
        return "\n".join(lines)

    # ── 시장 분석 ──

    async def _analyze(self, kwargs: dict[str, Any]) -> str:
        """수집 결과 기반 시장 분석."""
        query = kwargs.get("query", "")
        if not query:
            return "분석할 키워드(query)를 입력해주세요."

        # 먼저 데이터 수집
        search_result = await self._search({"query": query, "platform": "all", "count": 20})

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 플랫폼 마켓플레이스 시장 분석 전문가입니다.\n"
                "수집된 서비스 데이터를 기반으로 다음을 분석하세요:\n\n"
                "1. **시장 가격 포지셔닝**: 가격대별 분포, 평균/최빈 가격대\n"
                "2. **경쟁 강도**: 경쟁자 수, 포화도 판단\n"
                "3. **차별화 기회**: 빈틈(갭) 있는 영역, 차별화 포인트\n"
                "4. **진입 전략 제안**: 적정 가격대, 타겟 고객, 콘텐츠 전략\n\n"
                "한국어로 구체적으로 답변하세요. 수치를 포함해 분석하세요."
            ),
            user_prompt=f"검색 키워드: {query}\n\n수집 데이터:\n{search_result}",
        )

        return f"{search_result}\n\n---\n\n## 시장 분석\n\n{analysis}"

    # ── 가격대 분포 분석 ──

    async def _price_range(self, kwargs: dict[str, Any]) -> str:
        """가격대 구간별 분포 분석."""
        query = kwargs.get("query", "")
        if not query:
            return "분석할 키워드(query)를 입력해주세요."

        # 데이터 수집
        all_items: list[dict] = []
        for scraper in [self._scrape_kmong, self._scrape_taling, self._scrape_class101]:
            items = await scraper(query, 20)
            all_items.extend(items)
            await asyncio.sleep(1.5)

        if not all_items:
            return f"'{query}' 관련 서비스를 찾을 수 없습니다."

        # 가격 추출 (숫자만)
        prices = []
        for item in all_items:
            p = item.get("price")
            if isinstance(p, (int, float)) and p > 0:
                prices.append(int(p))

        if not prices:
            return "가격 정보가 포함된 서비스를 찾을 수 없습니다."

        # 구간별 분류
        ranges = {
            "5만원 이하": [p for p in prices if p <= 50000],
            "5~10만원": [p for p in prices if 50000 < p <= 100000],
            "10~30만원": [p for p in prices if 100000 < p <= 300000],
            "30만원 이상": [p for p in prices if p > 300000],
        }

        lines = [f"## 가격대 분포 분석: '{query}'\n"]
        lines.append(f"총 {len(prices)}개 서비스 (가격 확인 가능)\n")
        lines.append("| 가격대 | 서비스 수 | 비율 |")
        lines.append("|--------|----------|------|")
        for label, items in ranges.items():
            pct = len(items) / len(prices) * 100 if prices else 0
            lines.append(f"| {label} | {len(items)}건 | {pct:.1f}% |")

        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        max_price = max(prices)
        lines.append(f"\n- 평균 가격: {avg_price:,.0f}원")
        lines.append(f"- 최저 가격: {min_price:,}원")
        lines.append(f"- 최고 가격: {max_price:,}원")

        formatted = "\n".join(lines)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 가격 전략 전문가입니다.\n"
                "가격대 분포 데이터를 기반으로 다음을 분석하세요:\n"
                "1. 가장 경쟁이 치열한 가격대\n"
                "2. 비어있는(기회가 있는) 가격대\n"
                "3. 신규 진입 시 적정 가격 제안\n"
                "4. 프리미엄 vs 가성비 전략 비교\n"
                "한국어로 답변하세요."
            ),
            user_prompt=formatted,
        )

        return f"{formatted}\n\n---\n\n## 가격 전략 분석\n\n{analysis}"

    # ── 크몽 크롤링 ──

    async def _scrape_kmong(self, query: str, count: int) -> list[dict]:
        """크몽에서 서비스 검색."""
        url = f"https://kmong.com/search?q={query}"
        try:
            async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True) as client:
                resp = await client.get(url, timeout=15)
            if resp.status_code != 200:
                logger.warning("[크몽] HTTP %d", resp.status_code)
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            items: list[dict] = []

            # 크몽 검색 결과 카드 파싱
            cards = soup.select("div.search-card, article.gig-card, div.gig-wrapper, li.gig-list-item")
            if not cards:
                # 대체 선택자 시도
                cards = soup.select("[class*='card'], [class*='gig'], [class*='service']")

            for card in cards[:count]:
                title_el = card.select_one("h3, h4, [class*='title'], a[class*='title']")
                price_el = card.select_one("[class*='price'], span.price, .amount")
                rating_el = card.select_one("[class*='rating'], [class*='star'], .score")
                review_el = card.select_one("[class*='review'], [class*='count'], .review-count")

                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                price = self._extract_price(price_el.get_text(strip=True) if price_el else "")
                rating = rating_el.get_text(strip=True) if rating_el else "-"
                reviews = review_el.get_text(strip=True) if review_el else "-"

                items.append({
                    "platform": "크몽",
                    "title": title,
                    "price": price,
                    "rating": rating,
                    "reviews": reviews,
                })

            logger.info("[크몽] '%s' → %d건 수집", query, len(items))
            return items

        except Exception as e:
            logger.warning("[크몽] 크롤링 실패: %s", e)
            return []

    # ── 탈잉 크롤링 ──

    async def _scrape_taling(self, query: str, count: int) -> list[dict]:
        """탈잉에서 수업 검색."""
        url = f"https://taling.me/search/?query={query}"
        try:
            async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True) as client:
                resp = await client.get(url, timeout=15)
            if resp.status_code != 200:
                logger.warning("[탈잉] HTTP %d", resp.status_code)
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            items: list[dict] = []

            cards = soup.select("div.class-card, div.search-item, li.class-item, [class*='class-card']")
            if not cards:
                cards = soup.select("[class*='card'], [class*='class'], [class*='lesson']")

            for card in cards[:count]:
                title_el = card.select_one("h3, h4, [class*='title'], .class-title")
                price_el = card.select_one("[class*='price'], .price")
                rating_el = card.select_one("[class*='rating'], [class*='star']")
                student_el = card.select_one("[class*='student'], [class*='count']")

                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                price = self._extract_price(price_el.get_text(strip=True) if price_el else "")
                rating = rating_el.get_text(strip=True) if rating_el else "-"
                students = student_el.get_text(strip=True) if student_el else "-"

                items.append({
                    "platform": "탈잉",
                    "title": title,
                    "price": price,
                    "rating": rating,
                    "reviews": students,
                })

            logger.info("[탈잉] '%s' → %d건 수집", query, len(items))
            return items

        except Exception as e:
            logger.warning("[탈잉] 크롤링 실패: %s", e)
            return []

    # ── 클래스101 크롤링 ──

    async def _scrape_class101(self, query: str, count: int) -> list[dict]:
        """클래스101에서 클래스 검색."""
        url = f"https://class101.net/search?query={query}"
        try:
            async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True) as client:
                resp = await client.get(url, timeout=15)
            if resp.status_code != 200:
                logger.warning("[클래스101] HTTP %d", resp.status_code)
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            items: list[dict] = []

            cards = soup.select("div.product-card, div.class-card, [class*='product'], [class*='class-card']")
            if not cards:
                cards = soup.select("[class*='card'], a[class*='product']")

            for card in cards[:count]:
                title_el = card.select_one("h3, h4, [class*='title'], .product-title")
                price_el = card.select_one("[class*='price'], .price")
                rating_el = card.select_one("[class*='rating'], [class*='star']")
                student_el = card.select_one("[class*='student'], [class*='count'], [class*='like']")

                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                price = self._extract_price(price_el.get_text(strip=True) if price_el else "")
                rating = rating_el.get_text(strip=True) if rating_el else "-"
                students = student_el.get_text(strip=True) if student_el else "-"

                items.append({
                    "platform": "클래스101",
                    "title": title,
                    "price": price,
                    "rating": rating,
                    "reviews": students,
                })

            logger.info("[클래스101] '%s' → %d건 수집", query, len(items))
            return items

        except Exception as e:
            logger.warning("[클래스101] 크롤링 실패: %s", e)
            return []

    # ── 가격 추출 유틸 ──

    @staticmethod
    def _extract_price(text: str) -> int | str:
        """텍스트에서 숫자만 추출하여 가격 반환."""
        if not text:
            return "가격 미정"
        # 숫자와 쉼표만 남기기
        cleaned = re.sub(r"[^\d]", "", text)
        if cleaned:
            return int(cleaned)
        return "가격 미정"
