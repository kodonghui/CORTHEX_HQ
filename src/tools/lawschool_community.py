"""
법전원/LEET 커뮤니티 통합 크롤러.

3개 커뮤니티를 하나의 도구로 통합하여 LEET/로스쿨 관련 데이터를 수집합니다:
  1. DC 법전원갤 (gall.dcinside.com/mgallery/board/lists/?id=lawschool)
  2. 오르비 (orbi.kr)
  3. 서로연 (cafe.daum.net/snuleet — 카카오 검색 API 경유)

사용 방법:
  - action="search": 키워드로 전체/특정 커뮤니티 검색
  - action="trend": 전체 커뮤니티 트렌드 종합 분석
  - action="hot": 커뮤니티별 인기글 수집
  - action="compare": 커뮤니티 간 비교 분석

필요 환경변수:
  - KAKAO_REST_API_KEY: 서로연(다음카페) 검색용 (없으면 서로연 검색 불가)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.lawschool_community")

# ── 서로연 (다음 카페) ──
KAKAO_SEARCH_API = "https://dapi.kakao.com/v2/search/cafe"
SEOLYEON_CAFE_NAME = "서로연"  # 카카오 검색에서 카페명 필터

# ── DC 법전원갤 ──
DC_BASE = "https://gall.dcinside.com"
DC_LIST_URL = f"{DC_BASE}/mgallery/board/lists/"
DC_GALLERY_ID = "lawschool"

# ── 오르비 ──
ORBI_BASE = "https://orbi.kr"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

REQUEST_DELAY = 2.0

SOURCES = ["dc", "orbi", "seolyeon"]
SOURCE_NAMES = {
    "dc": "DC 법전원갤",
    "orbi": "오르비",
    "seolyeon": "서로연 (다음카페)",
}


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


class LawschoolCommunityTool(BaseTool):
    """법전원/LEET 커뮤니티 통합 크롤러."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "search")

        if action == "search":
            return await self._search(kwargs)
        elif action == "trend":
            return await self._trend(kwargs)
        elif action == "hot":
            return await self._hot(kwargs)
        elif action == "compare":
            return await self._compare(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능: search(검색), trend(트렌드), hot(인기글), compare(비교)"
            )

    # ── 공통 HTTP ──

    async def _fetch_html(self, url: str, params: dict | None = None,
                          headers: dict | None = None) -> str | None:
        httpx = _get_httpx()
        if httpx is None:
            return None
        default_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        if headers:
            default_headers.update(headers)
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                          headers=default_headers) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.text
        except Exception as e:
            logger.warning("요청 실패: %s — %s", url, e)
            return None

    async def _fetch_json(self, url: str, params: dict | None = None,
                           headers: dict | None = None) -> dict | None:
        httpx = _get_httpx()
        if httpx is None:
            return None
        try:
            async with httpx.AsyncClient(timeout=15, headers=headers or {}) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning("JSON 요청 실패: %s — %s", url, e)
            return None

    # ══════════════════════════════════════════════
    # DC 법전원갤 크롤링
    # ══════════════════════════════════════════════

    def _parse_dc_list(self, html: str) -> list[dict]:
        BeautifulSoup = _get_bs4()
        if BeautifulSoup is None:
            return self._parse_dc_list_regex(html)

        soup = BeautifulSoup(html, "html.parser")
        posts = []

        rows = soup.select("tr.ub-content.us-post") or soup.select("tr.ub-content")
        for row in rows:
            try:
                num_el = row.select_one("td.gall_num")
                if not num_el:
                    continue
                num_text = num_el.get_text(strip=True)
                if not num_text.isdigit():
                    continue

                title_el = row.select_one("td.gall_tit a")
                if not title_el:
                    continue

                # 댓글 수
                reply_el = row.select_one("td.gall_tit a.reply_numbox")
                reply_count = 0
                if reply_el:
                    rm = re.search(r"\d+", reply_el.get_text(strip=True))
                    if rm:
                        reply_count = int(rm.group())

                writer_el = row.select_one("td.gall_writer")
                date_el = row.select_one("td.gall_date")
                count_el = row.select_one("td.gall_count")
                rec_el = row.select_one("td.gall_recommend")

                posts.append({
                    "source": "dc",
                    "no": int(num_text),
                    "title": title_el.get_text(strip=True),
                    "writer": writer_el.get_text(strip=True) if writer_el else "",
                    "date": (date_el.get("title", date_el.get_text(strip=True))
                             if date_el else ""),
                    "views": int(count_el.get_text(strip=True) or 0)
                    if count_el and count_el.get_text(strip=True).isdigit() else 0,
                    "recommend": int(rec_el.get_text(strip=True) or 0)
                    if rec_el and rec_el.get_text(strip=True).isdigit() else 0,
                    "replies": reply_count,
                    "url": f"{DC_BASE}/mgallery/board/view/?id={DC_GALLERY_ID}&no={num_text}",
                })
            except Exception:
                continue
        return posts

    def _parse_dc_list_regex(self, html: str) -> list[dict]:
        posts = []
        pattern = re.compile(
            r'class="gall_num">(\d+)</td>.*?'
            r'class="gall_tit.*?<a[^>]*>([^<]+)</a>.*?'
            r'class="gall_count">(\d+)</td>.*?'
            r'class="gall_recommend">(\d+)</td>',
            re.DOTALL,
        )
        for m in pattern.finditer(html):
            no = m.group(1)
            posts.append({
                "source": "dc",
                "no": int(no),
                "title": m.group(2).strip(),
                "writer": "", "date": "",
                "views": int(m.group(3)),
                "recommend": int(m.group(4)),
                "replies": 0,
                "url": f"{DC_BASE}/mgallery/board/view/?id={DC_GALLERY_ID}&no={no}",
            })
        return posts

    async def _crawl_dc(self, query: str = "", pages: int = 3,
                         count: int = 30) -> list[dict]:
        all_posts: list[dict] = []
        for page in range(1, pages + 1):
            params: dict[str, Any] = {"id": DC_GALLERY_ID, "page": page}
            if query:
                params["s_type"] = "search_subject_memo"
                params["s_keyword"] = query
            html = await self._fetch_html(DC_LIST_URL, params=params,
                                           headers={"Referer": DC_BASE})
            if not html:
                break
            all_posts.extend(self._parse_dc_list(html))
            if len(all_posts) >= count:
                break
            if page < pages:
                await asyncio.sleep(REQUEST_DELAY)
        return all_posts[:count]

    # ══════════════════════════════════════════════
    # 오르비 크롤링
    # ══════════════════════════════════════════════

    def _parse_orbi_results(self, html: str) -> list[dict]:
        posts = []
        # 정규식으로 게시글 링크 추출
        pattern = re.compile(r'href="[^"]*?/(\d{8,})"[^>]*>([^<]{2,})</a>')
        seen = set()
        for m in pattern.finditer(html):
            pid = m.group(1)
            if pid in seen:
                continue
            seen.add(pid)
            title = m.group(2).strip()
            if len(title) < 2:
                continue
            posts.append({
                "source": "orbi",
                "no": int(pid),
                "title": title,
                "writer": "", "date": "",
                "views": 0, "recommend": 0, "replies": 0,
                "url": f"{ORBI_BASE}/{pid}",
            })
        return posts

    async def _crawl_orbi(self, query: str = "LEET",
                           count: int = 20) -> list[dict]:
        html = await self._fetch_html(
            f"{ORBI_BASE}/search",
            params={"q": query},
            headers={"Referer": ORBI_BASE},
        )
        if not html:
            return []
        return self._parse_orbi_results(html)[:count]

    # ══════════════════════════════════════════════
    # 서로연 (카카오 검색 API)
    # ══════════════════════════════════════════════

    async def _crawl_seolyeon(self, query: str = "LEET",
                               count: int = 20) -> list[dict]:
        api_key = os.getenv("KAKAO_REST_API_KEY", "")
        if not api_key:
            logger.warning("서로연 검색 불가: KAKAO_REST_API_KEY 미설정")
            return []

        # 카카오 카페 검색: "서로연" + 검색어로 서로연 카페 글을 검색
        search_query = f"서로연 {query}"
        data = await self._fetch_json(
            KAKAO_SEARCH_API,
            params={
                "query": search_query,
                "size": str(min(count, 50)),
                "sort": "recency",
            },
            headers={"Authorization": f"KakaoAK {api_key}"},
        )
        if not data:
            return []

        posts = []
        for doc in data.get("documents", []):
            cafe_name = doc.get("cafename", "")
            # 서로연 카페 글만 필터링
            if "서로" not in cafe_name and "snuleet" not in doc.get("url", ""):
                continue

            title = re.sub(r"<[^>]+>", "", doc.get("title", "")).strip()
            contents = re.sub(r"<[^>]+>", "", doc.get("contents", "")).strip()
            posts.append({
                "source": "seolyeon",
                "no": 0,
                "title": title,
                "writer": "",
                "date": doc.get("datetime", "")[:10],
                "views": 0, "recommend": 0, "replies": 0,
                "url": doc.get("url", ""),
                "preview": contents[:200],
                "cafe_name": cafe_name,
            })

        # 서로연 필터가 너무 엄격하면 전체 결과도 포함
        if not posts:
            for doc in data.get("documents", []):
                title = re.sub(r"<[^>]+>", "", doc.get("title", "")).strip()
                contents = re.sub(r"<[^>]+>", "", doc.get("contents", "")).strip()
                posts.append({
                    "source": "seolyeon",
                    "no": 0,
                    "title": title,
                    "writer": "",
                    "date": doc.get("datetime", "")[:10],
                    "views": 0, "recommend": 0, "replies": 0,
                    "url": doc.get("url", ""),
                    "preview": contents[:200],
                    "cafe_name": doc.get("cafename", ""),
                })

        return posts[:count]

    # ══════════════════════════════════════════════
    # 통합 액션
    # ══════════════════════════════════════════════

    def _parse_sources(self, kwargs: dict) -> list[str]:
        """소스 파라미터 파싱. 기본값: 전체."""
        src = kwargs.get("source", kwargs.get("sources", "all"))
        if src == "all":
            return SOURCES
        if isinstance(src, str):
            return [s.strip() for s in src.split(",") if s.strip() in SOURCES]
        return SOURCES

    def _format_posts(self, posts: list[dict], title: str) -> str:
        if not posts:
            return f"## {title}\n\n검색 결과가 없습니다."

        lines = [f"## {title} ({len(posts)}건)\n"]
        for i, p in enumerate(posts, 1):
            source_name = SOURCE_NAMES.get(p["source"], p["source"])
            stat_parts = []
            if p.get("recommend"):
                stat_parts.append(f"추천 {p['recommend']}")
            if p.get("views"):
                stat_parts.append(f"조회 {p['views']}")
            if p.get("replies"):
                stat_parts.append(f"댓글 {p['replies']}")
            stat = " | ".join(stat_parts) if stat_parts else ""

            line = f"**{i}. [{source_name}] {p['title']}**"
            if stat or p.get("date"):
                line += f"\n   {stat}"
                if p.get("date"):
                    line += f" | {p['date']}"
            if p.get("preview"):
                line += f"\n   > {p['preview'][:100]}"
            line += f"\n   {p['url']}"
            lines.append(line)

        return "\n\n".join(lines)

    # ── search ──

    async def _search(self, kwargs: dict) -> str:
        query = kwargs.get("query", "").strip()
        if not query:
            return "검색어(query)를 입력해주세요. 예: query='LEET 해설'"

        sources = self._parse_sources(kwargs)
        count = min(int(kwargs.get("count", 20)), 50)

        # 병렬 크롤링
        tasks = []
        if "dc" in sources:
            tasks.append(("dc", self._crawl_dc(query=query, count=count)))
        if "orbi" in sources:
            tasks.append(("orbi", self._crawl_orbi(query=query, count=count)))
        if "seolyeon" in sources:
            tasks.append(("seolyeon", self._crawl_seolyeon(query=query, count=count)))

        results = await asyncio.gather(*(t[1] for t in tasks), return_exceptions=True)

        all_posts = []
        errors = []
        for (src_name, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                errors.append(f"{SOURCE_NAMES[src_name]}: {result}")
            else:
                all_posts.extend(result)

        formatted = self._format_posts(all_posts, f"커뮤니티 검색: '{query}'")

        if errors:
            formatted += "\n\n**오류**:\n" + "\n".join(f"- {e}" for e in errors)

        return formatted

    # ── hot ──

    async def _hot(self, kwargs: dict) -> str:
        sources = self._parse_sources(kwargs)
        count = min(int(kwargs.get("count", 20)), 50)

        all_posts = []
        if "dc" in sources:
            posts = await self._crawl_dc(pages=3, count=count)
            posts.sort(key=lambda p: (p.get("recommend", 0), p.get("views", 0)),
                       reverse=True)
            all_posts.extend(posts[:count])
        if "orbi" in sources:
            html = await self._fetch_html(f"{ORBI_BASE}/list/hot",
                                           headers={"Referer": ORBI_BASE})
            if html:
                all_posts.extend(self._parse_orbi_results(html)[:count])
            await asyncio.sleep(REQUEST_DELAY)
        if "seolyeon" in sources:
            posts = await self._crawl_seolyeon(query="LEET 로스쿨", count=count)
            all_posts.extend(posts)

        return self._format_posts(all_posts, "커뮤니티 인기글")

    # ── trend ──

    async def _trend(self, kwargs: dict) -> str:
        topic = kwargs.get("topic", "LEET 해설 및 로스쿨 수험 트렌드")
        sources = self._parse_sources(kwargs)
        count = min(int(kwargs.get("count", 30)), 100)

        # 데이터 수집
        all_posts = []
        if "dc" in sources:
            all_posts.extend(await self._crawl_dc(pages=5, count=count))
        if "orbi" in sources:
            for kw in ["LEET", "리트", "로스쿨"]:
                posts = await self._crawl_orbi(query=kw, count=20)
                all_posts.extend(posts)
                await asyncio.sleep(REQUEST_DELAY)
        if "seolyeon" in sources:
            for kw in ["LEET", "해설", "합격"]:
                posts = await self._crawl_seolyeon(query=kw, count=15)
                all_posts.extend(posts)

        # 중복 제거 (URL 기준)
        seen_urls = set()
        unique_posts = []
        for p in all_posts:
            url = p.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_posts.append(p)

        if not unique_posts:
            return "커뮤니티에서 데이터를 수집하지 못했습니다."

        # 소스별 통계
        source_counts = {}
        for p in unique_posts:
            src = p.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1

        stats = " | ".join(
            f"{SOURCE_NAMES.get(s, s)}: {c}건"
            for s, c in source_counts.items()
        )

        # LLM 분석
        posts_text = "\n".join(
            f"[{SOURCE_NAMES.get(p['source'], '?')}] {p['title']}"
            + (f" (추천:{p.get('recommend', 0)} 조회:{p.get('views', 0)})" if p.get("views") else "")
            + (f" — {p.get('preview', '')[:80]}" if p.get("preview") else "")
            for p in unique_posts
        )

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 법학전문대학원(로스쿨) 입시 시장 분석 전문가입니다.\n"
                "3개 커뮤니티(DC 법전원갤, 오르비, 서로연)의 게시글을 종합 분석하세요.\n\n"
                "1. **핫토픽 TOP 5**: 가장 많이 논의되는 주제\n"
                "2. **커뮤니티별 특성**: 각 커뮤니티의 논의 성향 차이\n"
                "3. **LEET 관련**: 시험, 해설, 학원, 교재 관련 언급\n"
                "4. **감정 분석**: 수험생들의 전반적 분위기\n"
                "5. **경쟁사 언급**: 어떤 학원/교재/서비스가 언급되는지\n"
                "6. **리트마스터 시사점**: LEET Master 서비스 개선에 활용할 인사이트\n\n"
                "한국어로, 구체적 게시글을 인용하여 답변하세요."
            ),
            user_prompt=(
                f"분석 주제: {topic}\n"
                f"수집 현황: {stats}\n\n"
                f"## 커뮤니티 게시글 ({len(unique_posts)}건)\n\n{posts_text}"
            ),
        )

        return (
            f"## 법전원/LEET 커뮤니티 트렌드 분석\n\n"
            f"수집: {len(unique_posts)}건 ({stats})\n\n"
            f"---\n\n{analysis}"
        )

    # ── compare ──

    async def _compare(self, kwargs: dict) -> str:
        """커뮤니티 간 비교 분석."""
        topic = kwargs.get("topic", "LEET 해설 만족도")

        # 각 커뮤니티에서 데이터 수집
        dc_posts = await self._crawl_dc(query=topic, pages=3, count=20)
        await asyncio.sleep(REQUEST_DELAY)
        orbi_posts = await self._crawl_orbi(query=topic, count=20)
        await asyncio.sleep(REQUEST_DELAY)
        seolyeon_posts = await self._crawl_seolyeon(query=topic, count=20)

        sections = []
        for source, posts in [("dc", dc_posts), ("orbi", orbi_posts),
                               ("seolyeon", seolyeon_posts)]:
            name = SOURCE_NAMES[source]
            if posts:
                text = "\n".join(
                    f"- {p['title']}"
                    + (f" (추천:{p.get('recommend', 0)} 조회:{p.get('views', 0)})"
                       if p.get("views") else "")
                    for p in posts[:15]
                )
                sections.append(f"### {name} ({len(posts)}건)\n{text}")
            else:
                sections.append(f"### {name}\n(데이터 없음)")

        combined = "\n\n".join(sections)

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 온라인 커뮤니티 비교 분석 전문가입니다.\n"
                "3개 법전원/LEET 커뮤니티의 데이터를 비교 분석하세요.\n\n"
                "| 항목 | DC 법전원갤 | 오르비 | 서로연 |\n"
                "형식의 비교표를 포함하고, 각 커뮤니티의 특성, 사용자층, "
                "토론 성향, 정보 품질을 비교하세요.\n"
                "한국어로 답변하세요."
            ),
            user_prompt=f"비교 주제: {topic}\n\n{combined}",
        )

        return (
            f"## 커뮤니티 비교 분석: '{topic}'\n\n"
            f"{combined}\n\n---\n\n{analysis}"
        )
