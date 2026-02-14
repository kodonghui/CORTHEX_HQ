"""경쟁사 SNS 모니터 — 경쟁사의 SNS 활동을 자동 수집하고 분석하는 도구.

경쟁사의 네이버 블로그, 인스타그램, 유튜브 활동을
감시 목록으로 관리하며, 주기적으로 수집·분석합니다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.competitor_sns_monitor")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

# 감시 목록 파일 경로
WATCHLIST_PATH = Path("data/competitor_sns_watchlist.json")


def _load_watchlist() -> list[dict[str, Any]]:
    """감시 목록을 JSON 파일에서 로드합니다."""
    if not WATCHLIST_PATH.exists():
        return []
    try:
        with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_watchlist(watchlist: list[dict[str, Any]]) -> None:
    """감시 목록을 JSON 파일에 저장합니다."""
    WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=2)


class CompetitorSnsMonitorTool(BaseTool):
    """경쟁사의 SNS 활동을 자동 수집하고 분석하는 도구."""

    async def execute(self, **kwargs: Any) -> str:
        """
        경쟁사 SNS 모니터 실행.

        kwargs:
          - action: "add" | "remove" | "check" | "report" | "list"
          - name: 경쟁사 이름
          - blog_url: 네이버 블로그 URL (선택)
          - instagram: 인스타그램 사용자명 (선택)
          - youtube: 유튜브 채널 URL (선택)
        """
        action = kwargs.get("action", "list")

        if action == "add":
            return await self._add(kwargs)
        elif action == "remove":
            return await self._remove(kwargs)
        elif action == "check":
            return await self._check(kwargs)
        elif action == "report":
            return await self._report(kwargs)
        elif action == "list":
            return await self._list(kwargs)
        else:
            return f"알 수 없는 action: {action}\n사용 가능: add, remove, check, report, list"

    # ──────────────────────────────────────
    #  action: add
    # ──────────────────────────────────────

    async def _add(self, kwargs: dict[str, Any]) -> str:
        """감시 대상을 추가합니다."""
        name = kwargs.get("name", "")
        if not name:
            return "name(경쟁사 이름) 파라미터를 입력해주세요."

        blog_url = kwargs.get("blog_url", "")
        instagram = kwargs.get("instagram", "")
        youtube = kwargs.get("youtube", "")

        if not blog_url and not instagram and not youtube:
            return (
                "최소 하나의 SNS 채널을 지정해주세요.\n"
                "- blog_url: 네이버 블로그 URL\n"
                "- instagram: 인스타그램 사용자명\n"
                "- youtube: 유튜브 채널 URL"
            )

        watchlist = _load_watchlist()

        # 중복 확인
        for item in watchlist:
            if item["name"] == name:
                return f"'{name}'은(는) 이미 감시 목록에 있습니다."

        new_entry = {
            "name": name,
            "blog_url": blog_url,
            "instagram": instagram,
            "youtube": youtube,
            "added_at": datetime.now().isoformat(),
            "last_check": None,
        }
        watchlist.append(new_entry)
        _save_watchlist(watchlist)

        logger.info("[competitor_sns_monitor] 감시 대상 추가: %s", name)

        channels = []
        if blog_url:
            channels.append(f"- 블로그: {blog_url}")
        if instagram:
            channels.append(f"- 인스타그램: @{instagram}")
        if youtube:
            channels.append(f"- 유튜브: {youtube}")

        return (
            f"## 감시 대상 추가 완료\n"
            f"- 경쟁사: {name}\n"
            f"{''.join(ch + chr(10) for ch in channels)}"
            f"- 현재 감시 목록: {len(watchlist)}개"
        )

    # ──────────────────────────────────────
    #  action: remove
    # ──────────────────────────────────────

    async def _remove(self, kwargs: dict[str, Any]) -> str:
        """감시 대상을 제거합니다."""
        name = kwargs.get("name", "")
        if not name:
            return "name(경쟁사 이름) 파라미터를 입력해주세요."

        watchlist = _load_watchlist()
        original_len = len(watchlist)
        watchlist = [item for item in watchlist if item["name"] != name]

        if len(watchlist) == original_len:
            return f"'{name}'은(는) 감시 목록에 없습니다."

        _save_watchlist(watchlist)
        logger.info("[competitor_sns_monitor] 감시 대상 제거: %s", name)

        return f"## 감시 해제 완료\n- 제거된 경쟁사: {name}\n- 남은 감시 목록: {len(watchlist)}개"

    # ──────────────────────────────────────
    #  action: list
    # ──────────────────────────────────────

    async def _list(self, kwargs: dict[str, Any]) -> str:
        """감시 중인 경쟁사 목록을 보여줍니다."""
        watchlist = _load_watchlist()

        if not watchlist:
            return (
                "## 감시 목록\n\n"
                "감시 중인 경쟁사가 없습니다.\n"
                "action='add'로 감시 대상을 추가해주세요.\n\n"
                "예시:\n"
                "```\n"
                'action="add", name="메가로스쿨", blog_url="https://blog.naver.com/mega_leet"\n'
                "```"
            )

        lines = [
            "## 감시 중인 경쟁사 목록",
            "",
            "| 이름 | 블로그 | 인스타그램 | 유튜브 | 마지막 확인 |",
            "|------|--------|------------|--------|------------|",
        ]

        for item in watchlist:
            blog = "O" if item.get("blog_url") else "-"
            insta = f"@{item['instagram']}" if item.get("instagram") else "-"
            yt = "O" if item.get("youtube") else "-"
            last_check = item.get("last_check", "-") or "-"
            if last_check != "-":
                last_check = last_check[:10]  # 날짜만 표시
            lines.append(f"| {item['name']} | {blog} | {insta} | {yt} | {last_check} |")

        return "\n".join(lines)

    # ──────────────────────────────────────
    #  내부: 데이터 수집
    # ──────────────────────────────────────

    async def _fetch_blog_rss(self, blog_url: str) -> list[dict[str, str]]:
        """네이버 블로그의 RSS 피드에서 최근 게시물을 수집합니다."""
        # blog_url에서 블로그 ID 추출
        match = re.search(r"blog\.naver\.com/([^/?#]+)", blog_url)
        if not match:
            return []

        blog_id = match.group(1)
        rss_url = f"https://rss.blog.naver.com/{blog_id}.xml"

        try:
            async with httpx.AsyncClient(
                headers=_HEADERS, follow_redirects=True, timeout=15.0
            ) as client:
                resp = await client.get(rss_url)
                resp.raise_for_status()
                xml_text = resp.text
        except Exception as e:
            logger.warning("[competitor_sns_monitor] 블로그 RSS 수집 실패: %s", e)
            return []

        # XML 파싱
        posts: list[dict[str, str]] = []
        try:
            root = ET.fromstring(xml_text)
            # RSS 2.0 형식
            for item in root.findall(".//item"):
                title_el = item.find("title")
                link_el = item.find("link")
                pub_date_el = item.find("pubDate")
                posts.append({
                    "title": title_el.text if title_el is not None and title_el.text else "",
                    "link": link_el.text if link_el is not None and link_el.text else "",
                    "date": pub_date_el.text if pub_date_el is not None and pub_date_el.text else "",
                })
        except ET.ParseError:
            logger.warning("[competitor_sns_monitor] RSS XML 파싱 실패: %s", blog_url)

        return posts[:10]  # 최근 10개

    async def _fetch_instagram_info(self, username: str) -> dict[str, Any]:
        """인스타그램 프로필에서 공개 정보를 수집합니다."""
        url = f"https://www.instagram.com/{username}/"
        result: dict[str, Any] = {"username": username, "available": False}

        try:
            await asyncio.sleep(2.0)  # 차단 방지 딜레이
            async with httpx.AsyncClient(
                headers=_HEADERS, follow_redirects=True, timeout=10.0
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    result["error"] = f"HTTP {resp.status_code}"
                    return result

                text = resp.text

                # 팔로워 수 추출 시도
                follower_match = re.search(r'"edge_followed_by":\{"count":(\d+)\}', text)
                if follower_match:
                    result["followers"] = int(follower_match.group(1))

                # 게시물 수 추출 시도
                post_match = re.search(r'"edge_owner_to_timeline_media":\{"count":(\d+)', text)
                if post_match:
                    result["posts"] = int(post_match.group(1))

                result["available"] = True
        except Exception as e:
            result["error"] = str(e)
            logger.warning("[competitor_sns_monitor] 인스타그램 조회 실패 (%s): %s", username, e)

        return result

    async def _fetch_youtube_info(self, channel_url: str) -> dict[str, Any]:
        """유튜브 채널 페이지에서 기본 정보를 수집합니다."""
        result: dict[str, Any] = {"url": channel_url, "available": False}

        try:
            await asyncio.sleep(1.5)  # 딜레이
            async with httpx.AsyncClient(
                headers=_HEADERS, follow_redirects=True, timeout=15.0
            ) as client:
                resp = await client.get(channel_url)
                if resp.status_code != 200:
                    result["error"] = f"HTTP {resp.status_code}"
                    return result

                text = resp.text
                soup = BeautifulSoup(text, "html.parser")

                # 채널명 추출
                title_tag = soup.find("title")
                if title_tag:
                    result["channel_name"] = title_tag.get_text(strip=True).replace(" - YouTube", "")

                # 구독자 수 추출 시도
                sub_match = re.search(r'"subscriberCountText":\{"simpleText":"(.*?)"', text)
                if sub_match:
                    result["subscribers"] = sub_match.group(1)

                result["available"] = True
        except Exception as e:
            result["error"] = str(e)
            logger.warning("[competitor_sns_monitor] 유튜브 조회 실패: %s", e)

        return result

    # ──────────────────────────────────────
    #  action: check
    # ──────────────────────────────────────

    async def _check(self, kwargs: dict[str, Any]) -> str:
        """등록된 경쟁사의 최근 SNS 활동을 확인합니다."""
        watchlist = _load_watchlist()

        if not watchlist:
            return "감시 목록이 비어 있습니다. action='add'로 경쟁사를 추가해주세요."

        name_filter = kwargs.get("name", "")

        if name_filter:
            targets = [item for item in watchlist if item["name"] == name_filter]
            if not targets:
                return f"'{name_filter}'은(는) 감시 목록에 없습니다."
        else:
            targets = watchlist

        logger.info("[competitor_sns_monitor] check 시작: %d개 대상", len(targets))

        lines = ["## 경쟁사 SNS 활동 확인", ""]

        for target in targets:
            lines.append(f"### {target['name']}")
            lines.append("")

            # 블로그 확인
            if target.get("blog_url"):
                blog_posts = await self._fetch_blog_rss(target["blog_url"])
                if blog_posts:
                    lines.append(f"**블로그** ({target['blog_url']})")
                    lines.append(f"- 최근 게시물 {len(blog_posts)}개:")
                    for post in blog_posts[:5]:
                        lines.append(f"  - [{post['title']}]({post['link']}) ({post['date'][:10] if post['date'] else '날짜 없음'})")
                    # 게시 빈도 분석
                    if len(blog_posts) >= 2:
                        lines.append(f"  - 최근 {len(blog_posts)}개 글 기준 활동 중")
                else:
                    lines.append(f"**블로그**: RSS 수집 실패 또는 게시물 없음")
                lines.append("")

            # 인스타그램 확인
            if target.get("instagram"):
                insta_info = await self._fetch_instagram_info(target["instagram"])
                lines.append(f"**인스타그램** (@{target['instagram']})")
                if insta_info["available"]:
                    if "followers" in insta_info:
                        lines.append(f"  - 팔로워: {insta_info['followers']:,}명")
                    if "posts" in insta_info:
                        lines.append(f"  - 게시물: {insta_info['posts']:,}개")
                else:
                    lines.append(f"  - 조회 불가 (인스타그램 접근 제한)")
                lines.append("")

            # 유튜브 확인
            if target.get("youtube"):
                yt_info = await self._fetch_youtube_info(target["youtube"])
                lines.append(f"**유튜브** ({target['youtube']})")
                if yt_info["available"]:
                    if "channel_name" in yt_info:
                        lines.append(f"  - 채널명: {yt_info['channel_name']}")
                    if "subscribers" in yt_info:
                        lines.append(f"  - 구독자: {yt_info['subscribers']}")
                else:
                    lines.append(f"  - 조회 불가")
                lines.append("")

            # 마지막 확인 시간 갱신
            target["last_check"] = datetime.now().isoformat()

        # 감시 목록 업데이트 (마지막 확인 시간)
        _save_watchlist(watchlist)

        return "\n".join(lines)

    # ──────────────────────────────────────
    #  action: report
    # ──────────────────────────────────────

    async def _report(self, kwargs: dict[str, Any]) -> str:
        """경쟁사 SNS 전략 종합 보고서를 생성합니다."""
        name = kwargs.get("name", "all")

        watchlist = _load_watchlist()
        if not watchlist:
            return "감시 목록이 비어 있습니다. action='add'로 경쟁사를 추가해주세요."

        if name != "all":
            targets = [item for item in watchlist if item["name"] == name]
            if not targets:
                return f"'{name}'은(는) 감시 목록에 없습니다."
        else:
            targets = watchlist

        logger.info("[competitor_sns_monitor] report 시작: %d개 대상", len(targets))

        # 데이터 수집
        report_data: list[str] = []

        for target in targets:
            target_lines = [f"### {target['name']}"]

            if target.get("blog_url"):
                blog_posts = await self._fetch_blog_rss(target["blog_url"])
                if blog_posts:
                    target_lines.append(f"**블로그 활동**: 최근 {len(blog_posts)}개 글 확인")
                    for post in blog_posts[:5]:
                        target_lines.append(f"  - {post['title']} ({post['date'][:10] if post['date'] else '-'})")

            if target.get("instagram"):
                insta_info = await self._fetch_instagram_info(target["instagram"])
                if insta_info["available"]:
                    followers = insta_info.get("followers", "알 수 없음")
                    posts = insta_info.get("posts", "알 수 없음")
                    target_lines.append(f"**인스타그램**: 팔로워 {followers}, 게시물 {posts}")

            if target.get("youtube"):
                yt_info = await self._fetch_youtube_info(target["youtube"])
                if yt_info["available"]:
                    ch_name = yt_info.get("channel_name", "알 수 없음")
                    subs = yt_info.get("subscribers", "알 수 없음")
                    target_lines.append(f"**유튜브**: {ch_name}, 구독자 {subs}")

            report_data.append("\n".join(target_lines))

        collected_text = "\n\n".join(report_data)

        lines = [
            "## 경쟁사 SNS 전략 종합 보고서",
            f"- 보고서 생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"- 분석 대상: {', '.join(t['name'] for t in targets)}",
            "",
            collected_text,
        ]

        result_text = "\n".join(lines)

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 경쟁사 분석 전문가입니다. 아래 경쟁사 SNS 데이터를 분석하여:\n"
                "1. 각 경쟁사의 SNS 전략 요약\n"
                "2. 게시 빈도, 콘텐츠 유형, 주요 주제 분석\n"
                "3. 경쟁사 대비 우리의 강점과 약점\n"
                "4. 우리가 취해야 할 대응 전략 3가지\n"
                "5. 벤치마킹할 만한 포인트\n"
                "를 한국어로 작성하세요. 비개발자도 이해할 수 있게 쉽게 써주세요."
            ),
            user_prompt=result_text,
        )

        return f"{result_text}\n\n---\n\n### AI 경쟁사 전략 분석\n\n{analysis}"
