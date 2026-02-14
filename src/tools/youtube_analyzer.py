"""
유튜브 채널 분석기 Tool.

유튜브 채널의 영상 데이터를 수집하고 분석하여
콘텐츠 전략 인사이트를 제공합니다.

사용 방법:
  - action="channel": 채널 정보 + 최근 영상 분석
  - action="search": 유튜브 키워드 검색 결과 분석
  - action="trending": 특정 카테고리 인기 동영상

필요 환경변수: 없음
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.youtube_analyzer")


def _import_yt_dlp():
    """yt-dlp 라이브러리 임포트."""
    try:
        import yt_dlp
        return yt_dlp
    except ImportError:
        return None


class YoutubeAnalyzerTool(BaseTool):
    """유튜브 채널 분석 및 콘텐츠 전략 인사이트 도구."""

    _INSTALL_MSG = (
        "yt-dlp 라이브러리가 설치되지 않았습니다.\n"
        "다음 명령어로 설치하세요:\n"
        "```\npip install yt-dlp\n```"
    )

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "channel")

        if action == "channel":
            return await self._analyze_channel(kwargs)
        elif action == "search":
            return await self._search_videos(kwargs)
        elif action == "trending":
            return await self._get_trending(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "channel, search, trending 중 하나를 사용하세요."
            )

    # ── 채널 분석 ──

    async def _analyze_channel(self, kwargs: dict[str, Any]) -> str:
        yt_dlp = _import_yt_dlp()
        if yt_dlp is None:
            return self._INSTALL_MSG

        channel_url = kwargs.get("channel_url", "").strip()
        if not channel_url:
            return (
                "채널 URL을 입력해주세요.\n"
                "예: channel_url='https://www.youtube.com/@channelname'"
            )

        video_count = min(int(kwargs.get("video_count", 20)), 50)

        # 채널 영상 목록 추출 (다운로드 없이 메타데이터만)
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlistend": video_count,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)
        except Exception as e:
            logger.error("채널 정보 추출 실패: %s", e)
            return f"채널 정보를 가져올 수 없습니다: {e}\nURL이 올바른지 확인해주세요."

        if not info:
            return "채널 정보가 비어 있습니다."

        channel_title = info.get("title", info.get("uploader", "알 수 없음"))
        entries = info.get("entries", [])

        if not entries:
            return f"'{channel_title}' 채널에서 영상을 찾을 수 없습니다."

        # 각 영상의 상세 정보 수집
        videos = []
        for entry in entries:
            if not entry:
                continue
            videos.append({
                "title": entry.get("title", ""),
                "view_count": entry.get("view_count", 0) or 0,
                "duration": entry.get("duration", 0) or 0,
                "url": entry.get("url", entry.get("webpage_url", "")),
            })

        if not videos:
            return f"'{channel_title}' 채널의 영상 데이터를 파싱할 수 없습니다."

        # 통계 계산
        view_counts = [v["view_count"] for v in videos if v["view_count"] > 0]
        if view_counts:
            avg_views = sum(view_counts) / len(view_counts)
            sorted_views = sorted(view_counts)
            median_views = sorted_views[len(sorted_views) // 2]
            max_views = max(view_counts)
            min_views = min(view_counts)
        else:
            avg_views = median_views = max_views = min_views = 0

        # 상위/하위 영상
        sorted_by_views = sorted(videos, key=lambda x: x["view_count"], reverse=True)
        top_5 = sorted_by_views[:5]
        bottom_5 = sorted_by_views[-5:] if len(sorted_by_views) >= 5 else sorted_by_views

        top_lines = "\n".join(
            f"  {i}. [{v['title']}] — 조회수 {v['view_count']:,}회"
            for i, v in enumerate(top_5, 1)
        )
        bottom_lines = "\n".join(
            f"  {i}. [{v['title']}] — 조회수 {v['view_count']:,}회"
            for i, v in enumerate(bottom_5, 1)
        )

        report = (
            f"## 유튜브 채널 분석: {channel_title}\n\n"
            f"- **분석 영상 수**: {len(videos)}개\n"
            f"- **평균 조회수**: {avg_views:,.0f}회\n"
            f"- **조회수 중앙값**: {median_views:,}회\n"
            f"- **최고 조회수**: {max_views:,}회\n"
            f"- **최저 조회수**: {min_views:,}회\n\n"
            f"### 조회수 상위 5개 영상\n{top_lines}\n\n"
            f"### 조회수 하위 5개 영상\n{bottom_lines}"
        )

        # LLM 분석
        video_summary = "\n".join(
            f"- {v['title']} (조회수: {v['view_count']:,})"
            for v in sorted_by_views[:20]
        )

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 유튜브 콘텐츠 전략 분석가입니다.\n"
                "채널의 영상 데이터를 분석하여 다음을 정리하세요:\n"
                "1. 잘 되는 영상의 공통 패턴 (제목, 주제, 형식)\n"
                "2. 안 되는 영상의 공통 패턴\n"
                "3. 콘텐츠 전략 제안 (어떤 주제/형식이 효과적인지)\n"
                "4. 벤치마킹 인사이트\n"
                "한국어로 간결하게 보고하세요."
            ),
            user_prompt=(
                f"채널: {channel_title}\n"
                f"평균 조회수: {avg_views:,.0f}, 중앙값: {median_views:,}\n\n"
                f"영상 목록 (조회수순):\n{video_summary}"
            ),
        )

        return f"{report}\n\n---\n\n### 전략 분석\n\n{analysis}"

    # ── 키워드 검색 ──

    async def _search_videos(self, kwargs: dict[str, Any]) -> str:
        yt_dlp = _import_yt_dlp()
        if yt_dlp is None:
            return self._INSTALL_MSG

        query = kwargs.get("query", "").strip()
        if not query:
            return "검색 키워드(query)를 입력해주세요. 예: query='LEET 해설'"

        count = min(int(kwargs.get("count", 20)), 50)

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlistend": count,
        }

        search_url = f"ytsearch{count}:{query}"

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_url, download=False)
        except Exception as e:
            logger.error("유튜브 검색 실패: %s", e)
            return f"검색 실패: {e}"

        entries = info.get("entries", []) if info else []
        if not entries:
            return f"'{query}' 검색 결과가 없습니다."

        results = []
        for i, entry in enumerate(entries, 1):
            if not entry:
                continue
            title = entry.get("title", "")
            views = entry.get("view_count", 0) or 0
            uploader = entry.get("uploader", entry.get("channel", ""))
            duration = entry.get("duration", 0) or 0
            url = entry.get("url", entry.get("webpage_url", ""))

            dur_min = duration // 60 if duration else 0
            dur_sec = duration % 60 if duration else 0

            results.append(
                f"[{i}] {title}\n"
                f"    채널: {uploader} | 조회수: {views:,}회 | "
                f"길이: {dur_min}:{dur_sec:02d}\n"
                f"    URL: {url}"
            )

        result_text = "\n\n".join(results)

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 유튜브 콘텐츠 분석 전문가입니다.\n"
                "검색 결과를 분석하여 다음을 정리하세요:\n"
                "1. 검색 결과에서 발견되는 트렌드/패턴\n"
                "2. 조회수가 높은 영상의 공통 특징\n"
                "3. 콘텐츠 기회 (경쟁이 적거나 수요가 높은 영역)\n"
                "4. 우리가 만들 수 있는 콘텐츠 제안\n"
                "한국어로 보고하세요."
            ),
            user_prompt=f"검색어: '{query}'\n\n{result_text}",
        )

        return (
            f"## 유튜브 검색 결과: '{query}'\n\n"
            f"총 {len(results)}건\n\n{result_text}\n\n"
            f"---\n\n### 분석\n\n{analysis}"
        )

    # ── 인기 동영상 ──

    async def _get_trending(self, kwargs: dict[str, Any]) -> str:
        yt_dlp = _import_yt_dlp()
        if yt_dlp is None:
            return self._INSTALL_MSG

        category = kwargs.get("category", "all").strip().lower()

        # 한국 인기 동영상 URL
        if category == "education":
            trending_url = "https://www.youtube.com/feed/trending?bp=4gIcGhpnYW1pbmdfY29ycHVzX21vc3RfcG9wdWxhcg%3D%3D&gl=KR&hl=ko"
        else:
            trending_url = "https://www.youtube.com/feed/trending?gl=KR&hl=ko"

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlistend": 20,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(trending_url, download=False)
        except Exception as e:
            logger.error("인기 동영상 조회 실패: %s", e)
            return f"인기 동영상 조회 실패: {e}"

        entries = info.get("entries", []) if info else []
        if not entries:
            return "인기 동영상 데이터를 가져올 수 없습니다."

        results = []
        for i, entry in enumerate(entries[:20], 1):
            if not entry:
                continue
            title = entry.get("title", "")
            views = entry.get("view_count", 0) or 0
            uploader = entry.get("uploader", entry.get("channel", ""))

            results.append(
                f"[{i}] {title}\n"
                f"    채널: {uploader} | 조회수: {views:,}회"
            )

        result_text = "\n\n".join(results)
        cat_label = "교육" if category == "education" else "전체"

        analysis = await self._llm_call(
            system_prompt=(
                "당신은 유튜브 트렌드 분석 전문가입니다.\n"
                "인기 동영상 목록을 분석하여 다음을 정리하세요:\n"
                "1. 현재 유행하는 콘텐츠 주제/형식\n"
                "2. 교육 분야의 트렌드 (해당 시)\n"
                "3. 벤치마킹할 만한 채널/콘텐츠\n"
                "한국어로 보고하세요."
            ),
            user_prompt=f"카테고리: {cat_label}\n\n{result_text}",
        )

        return (
            f"## 유튜브 인기 동영상 ({cat_label})\n\n"
            f"{result_text}\n\n"
            f"---\n\n### 트렌드 분석\n\n{analysis}"
        )
