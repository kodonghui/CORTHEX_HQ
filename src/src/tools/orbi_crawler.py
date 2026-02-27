"""
오르비(Orbi) LEET/로스쿨 커뮤니티 크롤러.

orbi.kr에서 LEET/법학 관련 게시글을 수집하고
LLM으로 수험생 트렌드를 분석합니다.

사용 방법:
  - action="search": LEET 관련 키워드 검색
  - action="hot": 인기 게시글 수집
  - action="trend": 최근 글에서 트렌드 분석
  - action="read": 특정 게시글 본문 읽기

필요 환경변수: 없음 (공개 게시판)
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.orbi_crawler")

BASE_URL = "https://orbi.kr"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": BASE_URL,
}

# 요청 간 딜레이 (초)
REQUEST_DELAY = 2.0

# LEET/로스쿨 관련 기본 검색 키워드
LEET_KEYWORDS = [
    "LEET", "리트", "로스쿨", "법전원", "법학전문대학원",
    "추리논증", "언어이해", "법학적성",
]


def _get_httpx():
    try:
        import httpx
        return httpx
    except ImportError:
        return None


def _get_bs4():
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup
    except ImportError:
        return None


class OrbiCrawlerTool(BaseTool):
    """오르비 LEET/로스쿨 크롤러 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "search")

        if action == "search":
            return await self._search_posts(kwargs)
        elif action == "hot":
            return await self._get_hot_posts(kwargs)
        elif action == "trend":
            return await self._analyze_trend(kwargs)
        elif action == "read":
            return await self._read_post(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능: search(검색), hot(인기글), trend(트렌드 분석), read(글 읽기)"
            )

    # ── HTTP 요청 ──

    async def _fetch_html(self, url: str, params: dict | None = None) -> str | None:
        httpx = _get_httpx()
        if httpx is None:
            return None

        try:
            async with httpx.AsyncClient(
                timeout=15,
                follow_redirects=True,
                headers=HEADERS,
            ) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.text
        except Exception as e:
            logger.warning("오르비 요청 실패: %s — %s", url, e)
            return None

    # ── HTML 파싱 ──

    def _parse_search_results(self, html: str) -> list[dict]:
        """오르비 검색 결과 HTML에서 게시글 정보를 추출."""
        BeautifulSoup = _get_bs4()
        if BeautifulSoup is None:
            return self._parse_search_regex(html)

        soup = BeautifulSoup(html, "html.parser")
        posts = []

        # 오르비 검색 결과 카드
        items = soup.select("div.search-result-item, article.board-item, div.list-item, li.article-list-item")
        if not items:
            # 전체 게시글 목록 구조 시도
            items = soup.select("a[href*='/0']")

        for item in items:
            try:
                # 링크 추출
                link_el = item if item.name == "a" else item.select_one("a[href]")
                if not link_el or not link_el.get("href"):
                    continue

                href = link_el["href"]
                # 오르비 게시글 URL: /00021590375 형태
                post_id_match = re.search(r"/(\d{8,})", href)
                if not post_id_match:
                    continue

                post_id = post_id_match.group(1)
                url = f"{BASE_URL}/{post_id}"

                # 제목
                title_el = item.select_one("h3, h2, .title, .article-title, span.title")
                if not title_el:
                    title_el = link_el
                title = title_el.get_text(strip=True)
                if not title or len(title) < 2:
                    continue

                # 조회수, 추천, 댓글
                views = 0
                likes = 0
                replies = 0

                stat_els = item.select("span.count, span.stat, span.num")
                for stat_el in stat_els:
                    stat_text = stat_el.get_text(strip=True)
                    num_match = re.search(r"(\d+)", stat_text)
                    if not num_match:
                        continue
                    val = int(num_match.group(1))
                    parent_class = " ".join(stat_el.get("class", []))
                    if "view" in parent_class or "hit" in parent_class:
                        views = val
                    elif "like" in parent_class or "recommend" in parent_class:
                        likes = val
                    elif "reply" in parent_class or "comment" in parent_class:
                        replies = val

                # 날짜
                date_el = item.select_one("time, span.date, span.time")
                date = date_el.get_text(strip=True) if date_el else ""

                # 작성자
                writer_el = item.select_one("span.author, span.nick, span.username")
                writer = writer_el.get_text(strip=True) if writer_el else ""

                posts.append({
                    "id": post_id,
                    "title": title,
                    "writer": writer,
                    "date": date,
                    "views": views,
                    "likes": likes,
                    "replies": replies,
                    "url": url,
                })
            except Exception:
                continue

        return posts

    def _parse_search_regex(self, html: str) -> list[dict]:
        """BeautifulSoup 없을 때 정규식 폴백."""
        posts = []
        # 오르비 게시글 링크 패턴
        pattern = re.compile(r'href="[^"]*?/(\d{8,})"[^>]*>([^<]+)</a>')
        seen = set()
        for m in pattern.finditer(html):
            post_id = m.group(1)
            if post_id in seen:
                continue
            seen.add(post_id)
            title = m.group(2).strip()
            if len(title) < 2:
                continue
            posts.append({
                "id": post_id,
                "title": title,
                "writer": "",
                "date": "",
                "views": 0,
                "likes": 0,
                "replies": 0,
                "url": f"{BASE_URL}/{post_id}",
            })
        return posts

    def _parse_post_body(self, html: str) -> dict:
        """게시글 본문 파싱."""
        BeautifulSoup = _get_bs4()
        if BeautifulSoup is None:
            title_m = re.search(r"<title>([^<]+)</title>", html)
            body_m = re.search(r'class="content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
            title = title_m.group(1).strip() if title_m else "(제목 없음)"
            body_text = re.sub(r"<[^>]+>", "", body_m.group(1)).strip() if body_m else "(본문 파싱 실패)"
            return {"title": title, "body": body_text[:3000]}

        soup = BeautifulSoup(html, "html.parser")

        # 제목
        title_el = soup.select_one("h1.title, h1.article-title, div.title h1, title")
        title = title_el.get_text(strip=True) if title_el else "(제목 없음)"
        # <title>에서 " - 오르비" 접미사 제거
        title = re.sub(r"\s*[-|]\s*오르비.*$", "", title)

        # 본문
        body_el = soup.select_one(
            "div.content-body, div.article-content, div.fr-view, "
            "div.content, article .body"
        )
        if body_el:
            for img in body_el.find_all("img"):
                img.replace_with("[이미지]")
            body_text = body_el.get_text(separator="\n", strip=True)
        else:
            body_text = "(본문 파싱 실패)"

        # 작성자
        writer_el = soup.select_one("span.author, span.nick, a.author")
        writer = writer_el.get_text(strip=True) if writer_el else ""

        # 날짜
        date_el = soup.select_one("time, span.date")
        date = ""
        if date_el:
            date = date_el.get("datetime", date_el.get_text(strip=True))

        return {
            "title": title,
            "body": body_text[:3000],
            "writer": writer,
            "date": date,
        }

    # ── 검색 ──

    async def _search_posts(self, kwargs: dict) -> str:
        """키워드로 게시글 검색."""
        query = kwargs.get("query", "").strip()
        if not query:
            # LEET 기본 검색
            query = "LEET"

        count = min(int(kwargs.get("count", 20)), 50)

        # 오르비 검색 URL
        search_url = f"{BASE_URL}/search"
        html = await self._fetch_html(search_url, params={"q": query})
        if not html:
            return f"오르비에서 '{query}' 검색에 실패했습니다."

        posts = self._parse_search_results(html)

        if not posts:
            # 구글 사이트 검색 폴백
            return (
                f"오르비에서 '{query}' 직접 검색 결과가 없습니다.\n"
                "오르비 검색 페이지 구조가 변경되었을 수 있습니다.\n"
                "real_web_search 도구로 'site:orbi.kr LEET' 검색을 시도해보세요."
            )

        result_posts = posts[:count]
        lines = [f"## 오르비 검색: '{query}' ({len(result_posts)}건)\n"]
        for i, p in enumerate(result_posts, 1):
            stat = f"추천 {p['likes']} | 조회 {p['views']} | 댓글 {p['replies']}"
            lines.append(
                f"**{i}. {p['title']}**\n"
                f"   {stat} | {p['date']}\n"
                f"   {p['url']}"
            )

        return "\n\n".join(lines)

    # ── 인기글 ──

    async def _get_hot_posts(self, kwargs: dict) -> str:
        """오르비 인기글 수집."""
        count = min(int(kwargs.get("count", 20)), 50)

        # 오르비 인기글 페이지
        html = await self._fetch_html(f"{BASE_URL}/list/hot")
        if not html:
            return "오르비 인기글을 가져올 수 없습니다."

        posts = self._parse_search_results(html)

        if not posts:
            return "오르비 인기글 파싱에 실패했습니다. 사이트 구조가 변경되었을 수 있습니다."

        # LEET/로스쿨 관련 필터링 (옵션)
        filter_leet = kwargs.get("filter_leet", False)
        if filter_leet:
            leet_posts = [
                p for p in posts
                if any(kw.lower() in p["title"].lower() for kw in LEET_KEYWORDS)
            ]
            if leet_posts:
                posts = leet_posts

        result_posts = posts[:count]
        lines = [f"## 오르비 인기글 ({len(result_posts)}건)\n"]
        for i, p in enumerate(result_posts, 1):
            stat = f"추천 {p['likes']} | 조회 {p['views']} | 댓글 {p['replies']}"
            lines.append(
                f"**{i}. {p['title']}**\n"
                f"   {stat} | {p['date']}\n"
                f"   {p['url']}"
            )

        return "\n\n".join(lines)

    # ── 트렌드 분석 ──

    async def _analyze_trend(self, kwargs: dict) -> str:
        """LEET 관련 게시글에서 트렌드를 분석."""
        topic = kwargs.get("topic", "LEET 해설 및 로스쿨 수험 트렌드")

        # 여러 LEET 키워드로 검색하여 데이터 수집
        all_posts: list[dict] = []
        keywords = kwargs.get("keywords", "LEET,리트,로스쿨,법전원").split(",")

        for kw in keywords[:4]:
            html = await self._fetch_html(
                f"{BASE_URL}/search",
                params={"q": kw.strip()},
            )
            if html:
                posts = self._parse_search_results(html)
                all_posts.extend(posts)
            await asyncio.sleep(REQUEST_DELAY)

        # 중복 제거
        seen_ids = set()
        unique_posts = []
        for p in all_posts:
            if p["id"] not in seen_ids:
                seen_ids.add(p["id"])
                unique_posts.append(p)

        if not unique_posts:
            return "오르비에서 LEET 관련 게시글을 찾을 수 없습니다."

        posts_text = "\n".join(
            f"[{i}] {p['title']} (추천:{p['likes']} 조회:{p['views']} {p['date']})"
            for i, p in enumerate(unique_posts, 1)
        )

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 LEET/로스쿨 입시 시장 분석 전문가입니다.\n"
                "오르비(교육 커뮤니티)의 LEET 관련 게시글을 분석하여 다음을 정리하세요:\n\n"
                "1. **주요 관심사 TOP 5**: 수험생들이 가장 많이 논의하는 주제\n"
                "2. **LEET 시험 관련**: 시험 난이도, 영역별 반응, 합격선 예측 등\n"
                "3. **학원/교재 언급**: 어떤 학원과 교재가 언급되는지\n"
                "4. **수험생 감정**: 불안, 스트레스, 동기부여 관련 분위기\n"
                "5. **리트마스터 시사점**: 서비스 개선에 활용할 수 있는 인사이트\n\n"
                "한국어로 답변하세요."
            ),
            user_prompt=(
                f"분석 주제: {topic}\n\n"
                f"## 오르비 LEET 관련 게시글 ({len(unique_posts)}건)\n\n{posts_text}"
            ),
        )

        return (
            f"## 오르비 LEET 트렌드 분석\n\n"
            f"수집: {len(unique_posts)}개 게시글 (키워드: {', '.join(keywords)})\n\n"
            f"---\n\n{analysis}"
        )

    # ── 게시글 읽기 ──

    async def _read_post(self, kwargs: dict) -> str:
        """특정 게시글 본문을 읽습니다."""
        post_id = kwargs.get("post_id", kwargs.get("id", ""))
        if not post_id:
            return "게시글 ID(post_id)를 입력해주세요. 예: post_id='00021590375'"

        url = kwargs.get("url", f"{BASE_URL}/{post_id}")
        html = await self._fetch_html(url)
        if not html:
            return f"게시글 {post_id}을(를) 가져올 수 없습니다."

        data = self._parse_post_body(html)

        return (
            f"## 오르비 게시글 #{post_id}\n\n"
            f"**제목**: {data['title']}\n"
            f"**작성자**: {data.get('writer', '')}\n"
            f"**날짜**: {data.get('date', '')}\n\n"
            f"---\n\n{data['body']}"
        )
