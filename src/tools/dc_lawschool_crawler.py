"""
DCinside 법학전문대학원 마이너갤러리 크롤러.

법전원갤(법학전문대학원 마이너갤러리)에서 게시글 목록과 본문을 수집하고
LLM으로 LEET/로스쿨 트렌드를 분석합니다.

사용 방법:
  - action="hot": 인기글 수집 (조회수/추천 높은 글)
  - action="search": 키워드 검색
  - action="trend": 최근 글에서 트렌드 분석
  - action="read": 특정 게시글 본문 읽기

필요 환경변수: 없음 (공개 게시판)
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import quote, urljoin

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.dc_lawschool")

GALLERY_ID = "lawschool"
BASE_URL = "https://gall.dcinside.com"
LIST_URL = f"{BASE_URL}/mgallery/board/lists/"
VIEW_URL = f"{BASE_URL}/mgallery/board/view/"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.5",
    "Referer": BASE_URL,
}

# 요청 간 딜레이 (초) — robots.txt Crawl-delay 준수
REQUEST_DELAY = 2.0


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


class DcLawschoolCrawlerTool(BaseTool):
    """DCinside 법전원갤 크롤러 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "hot")

        if action == "hot":
            return await self._get_hot_posts(kwargs)
        elif action == "search":
            return await self._search_posts(kwargs)
        elif action == "trend":
            return await self._analyze_trend(kwargs)
        elif action == "read":
            return await self._read_post(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능: hot(인기글), search(검색), trend(트렌드 분석), read(글 읽기)"
            )

    # ── HTML 파싱 헬퍼 ──

    async def _fetch_html(self, url: str, params: dict | None = None) -> str | None:
        """URL에서 HTML을 가져옵니다."""
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
            logger.warning("DC 갤러리 요청 실패: %s — %s", url, e)
            return None

    def _parse_post_list(self, html: str) -> list[dict]:
        """게시글 목록 HTML에서 게시글 정보를 추출합니다."""
        BeautifulSoup = _get_bs4()
        if BeautifulSoup is None:
            return self._parse_post_list_regex(html)

        soup = BeautifulSoup(html, "html.parser")
        posts = []

        # DC 갤러리 게시글 목록: <tr class="ub-content us-post">
        rows = soup.select("tr.ub-content.us-post")
        if not rows:
            # 마이너갤러리 다른 구조 시도
            rows = soup.select("tr.ub-content")

        for row in rows:
            try:
                # 글번호
                num_el = row.select_one("td.gall_num")
                if not num_el:
                    continue
                num_text = num_el.get_text(strip=True)
                # 공지, 설문 등 숫자가 아닌 것은 건너뜀
                if not num_text.isdigit():
                    continue
                post_no = int(num_text)

                # 제목
                title_el = row.select_one("td.gall_tit a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)

                # 댓글 수
                reply_el = row.select_one("td.gall_tit a.reply_numbox")
                reply_count = 0
                if reply_el:
                    reply_text = reply_el.get_text(strip=True)
                    reply_match = re.search(r"\d+", reply_text)
                    if reply_match:
                        reply_count = int(reply_match.group())

                # 작성자
                writer_el = row.select_one("td.gall_writer")
                writer = writer_el.get_text(strip=True) if writer_el else ""

                # 날짜
                date_el = row.select_one("td.gall_date")
                date = date_el.get("title", date_el.get_text(strip=True)) if date_el else ""

                # 조회수
                count_el = row.select_one("td.gall_count")
                view_count = 0
                if count_el:
                    vc_text = count_el.get_text(strip=True)
                    if vc_text.isdigit():
                        view_count = int(vc_text)

                # 추천수
                recommend_el = row.select_one("td.gall_recommend")
                recommend = 0
                if recommend_el:
                    rec_text = recommend_el.get_text(strip=True)
                    if rec_text.isdigit():
                        recommend = int(rec_text)

                posts.append({
                    "no": post_no,
                    "title": title,
                    "writer": writer,
                    "date": date,
                    "views": view_count,
                    "recommend": recommend,
                    "replies": reply_count,
                    "url": f"{VIEW_URL}?id={GALLERY_ID}&no={post_no}",
                })
            except Exception:
                continue

        return posts

    def _parse_post_list_regex(self, html: str) -> list[dict]:
        """BeautifulSoup 없을 때 정규식으로 파싱 (폴백)."""
        posts = []
        # 간단한 정규식 기반 파싱
        pattern = re.compile(
            r'class="gall_num">(\d+)</td>.*?'
            r'class="gall_tit.*?<a[^>]*>([^<]+)</a>.*?'
            r'class="gall_count">(\d+)</td>.*?'
            r'class="gall_recommend">(\d+)</td>',
            re.DOTALL,
        )
        for m in pattern.finditer(html):
            post_no = int(m.group(1))
            posts.append({
                "no": post_no,
                "title": m.group(2).strip(),
                "writer": "",
                "date": "",
                "views": int(m.group(3)),
                "recommend": int(m.group(4)),
                "replies": 0,
                "url": f"{VIEW_URL}?id={GALLERY_ID}&no={post_no}",
            })
        return posts

    def _parse_post_body(self, html: str) -> dict:
        """게시글 본문 HTML에서 제목, 내용, 댓글 수를 추출합니다."""
        BeautifulSoup = _get_bs4()
        if BeautifulSoup is None:
            # 정규식 폴백
            title_m = re.search(r'<span class="title_subject">([^<]+)</span>', html)
            body_m = re.search(
                r'<div class="write_div"[^>]*>(.*?)</div>',
                html,
                re.DOTALL,
            )
            title = title_m.group(1).strip() if title_m else "(제목 파싱 실패)"
            body_html = body_m.group(1) if body_m else ""
            body_text = re.sub(r"<[^>]+>", "", body_html).strip()
            return {"title": title, "body": body_text[:2000]}

        soup = BeautifulSoup(html, "html.parser")

        # 제목
        title_el = soup.select_one("span.title_subject")
        title = title_el.get_text(strip=True) if title_el else "(제목 없음)"

        # 본문
        body_el = soup.select_one("div.write_div")
        if body_el:
            # 이미지 태그를 [이미지]로 치환
            for img in body_el.find_all("img"):
                img.replace_with("[이미지]")
            body_text = body_el.get_text(separator="\n", strip=True)
        else:
            body_text = "(본문 파싱 실패)"

        # 작성자, 날짜
        writer_el = soup.select_one("div.gall_writer span.nickname")
        writer = writer_el.get_text(strip=True) if writer_el else ""

        date_el = soup.select_one("span.gall_date")
        date = date_el.get("title", date_el.get_text(strip=True)) if date_el else ""

        return {
            "title": title,
            "body": body_text[:3000],
            "writer": writer,
            "date": date,
        }

    # ── 인기글 수집 ──

    async def _get_hot_posts(self, kwargs: dict) -> str:
        """인기글(조회수/추천 높은 글) 수집."""
        count = min(int(kwargs.get("count", 30)), 100)
        pages = min(int(kwargs.get("pages", 3)), 10)

        all_posts: list[dict] = []
        for page in range(1, pages + 1):
            html = await self._fetch_html(
                LIST_URL,
                params={"id": GALLERY_ID, "page": page},
            )
            if not html:
                break
            posts = self._parse_post_list(html)
            all_posts.extend(posts)
            if page < pages:
                await asyncio.sleep(REQUEST_DELAY)

        if not all_posts:
            return (
                "DC 법전원갤 게시글을 가져올 수 없습니다.\n"
                "사이트 구조가 변경되었거나 접속이 차단되었을 수 있습니다."
            )

        # 조회수+추천 기준 정렬
        all_posts.sort(key=lambda p: (p["recommend"], p["views"]), reverse=True)
        top_posts = all_posts[:count]

        lines = [f"## DC 법전원갤 인기글 (상위 {len(top_posts)}개)\n"]
        for i, p in enumerate(top_posts, 1):
            lines.append(
                f"**{i}. {p['title']}**\n"
                f"   추천 {p['recommend']} | 조회 {p['views']} | 댓글 {p['replies']} | "
                f"{p['date']} | {p['writer']}\n"
                f"   {p['url']}"
            )

        return "\n\n".join(lines)

    # ── 키워드 검색 ──

    async def _search_posts(self, kwargs: dict) -> str:
        """키워드로 게시글 검색."""
        query = kwargs.get("query", "").strip()
        if not query:
            return "검색어(query)를 입력해주세요. 예: query='LEET 해설'"

        count = min(int(kwargs.get("count", 20)), 50)
        pages = min(int(kwargs.get("pages", 3)), 5)
        # DC 검색 타입: search_subject_memo=제목+내용, search_subject=제목
        search_type = kwargs.get("search_type", "search_subject_memo")

        all_posts: list[dict] = []
        for page in range(1, pages + 1):
            html = await self._fetch_html(
                LIST_URL,
                params={
                    "id": GALLERY_ID,
                    "page": page,
                    "s_type": search_type,
                    "s_keyword": query,
                },
            )
            if not html:
                break
            posts = self._parse_post_list(html)
            all_posts.extend(posts)
            if len(all_posts) >= count:
                break
            if page < pages:
                await asyncio.sleep(REQUEST_DELAY)

        if not all_posts:
            return f"'{query}' 검색 결과가 없습니다."

        result_posts = all_posts[:count]

        lines = [f"## DC 법전원갤 검색: '{query}' ({len(result_posts)}건)\n"]
        for i, p in enumerate(result_posts, 1):
            lines.append(
                f"**{i}. {p['title']}**\n"
                f"   추천 {p['recommend']} | 조회 {p['views']} | 댓글 {p['replies']} | "
                f"{p['date']}\n"
                f"   {p['url']}"
            )

        return "\n\n".join(lines)

    # ── 트렌드 분석 ──

    async def _analyze_trend(self, kwargs: dict) -> str:
        """최근 게시글에서 LEET/로스쿨 트렌드를 LLM으로 분석."""
        pages = min(int(kwargs.get("pages", 5)), 10)
        topic = kwargs.get("topic", "LEET 해설 및 로스쿨 수험 트렌드")

        all_posts: list[dict] = []
        for page in range(1, pages + 1):
            html = await self._fetch_html(
                LIST_URL,
                params={"id": GALLERY_ID, "page": page},
            )
            if not html:
                break
            posts = self._parse_post_list(html)
            all_posts.extend(posts)
            if page < pages:
                await asyncio.sleep(REQUEST_DELAY)

        if not all_posts:
            return "게시글을 가져올 수 없습니다."

        # 게시글 목록을 텍스트로 변환
        posts_text = "\n".join(
            f"[{i}] {p['title']} (추천:{p['recommend']} 조회:{p['views']} 댓글:{p['replies']} {p['date']})"
            for i, p in enumerate(all_posts, 1)
        )

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 법학전문대학원(로스쿨) 입시 시장 분석 전문가입니다.\n"
                "DCinside 법전원갤러리의 게시글 제목들을 분석하여 다음을 정리하세요:\n\n"
                "1. **핫토픽 TOP 5**: 가장 많이 논의되는 주제 (게시글 수/조회수 기준)\n"
                "2. **LEET 관련 키워드**: LEET 시험, 해설, 학원, 교재 관련 언급\n"
                "3. **감정 분석**: 전반적인 분위기 (불안, 자신감, 불만 등)\n"
                "4. **경쟁사/학원 언급**: 메가, 이그잼, 해커스 등 어떤 브랜드가 언급되는지\n"
                "5. **사업 인사이트**: 리트마스터(LEET Master) 서비스에 활용할 수 있는 시사점\n\n"
                "수치와 구체적 게시글 제목을 인용하여 근거를 제시하세요.\n"
                "한국어로 답변하세요."
            ),
            user_prompt=(
                f"분석 주제: {topic}\n\n"
                f"## DC 법전원갤 최근 게시글 ({len(all_posts)}건)\n\n{posts_text}"
            ),
        )

        return (
            f"## DC 법전원갤 트렌드 분석\n\n"
            f"수집: 최근 {pages}페이지, {len(all_posts)}개 게시글\n\n"
            f"---\n\n{analysis}"
        )

    # ── 게시글 읽기 ──

    async def _read_post(self, kwargs: dict) -> str:
        """특정 게시글 본문을 읽습니다."""
        post_no = kwargs.get("post_no", kwargs.get("no", ""))
        if not post_no:
            return "게시글 번호(post_no)를 입력해주세요."

        html = await self._fetch_html(
            VIEW_URL,
            params={"id": GALLERY_ID, "no": post_no},
        )
        if not html:
            return f"게시글 {post_no}을(를) 가져올 수 없습니다."

        data = self._parse_post_body(html)

        return (
            f"## DC 법전원갤 게시글 #{post_no}\n\n"
            f"**제목**: {data['title']}\n"
            f"**작성자**: {data.get('writer', '')}\n"
            f"**날짜**: {data.get('date', '')}\n\n"
            f"---\n\n{data['body']}"
        )
