"""
다음 카페 검색/읽기 Tool.

카카오 검색 API를 사용하여 다음 카페 글을 검색하고,
검색 결과를 LLM이 분석·요약합니다.

사용 방법:
  - action="search": 키워드로 다음 카페 글 검색
  - action="read": 특정 카페 글 URL의 본문 크롤링 (공개 글만)

필요 환경변수:
  - KAKAO_REST_API_KEY: 카카오 개발자 센터 REST API 키
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.daum_cafe")

KAKAO_SEARCH_API = "https://dapi.kakao.com/v2/search/cafe"


class DaumCafeTool(BaseTool):
    """다음 카페 검색 및 글 읽기 도구."""

    @property
    def _headers(self) -> dict[str, str]:
        key = os.getenv("KAKAO_REST_API_KEY", "")
        return {"Authorization": f"KakaoAK {key}"}

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

        if not os.getenv("KAKAO_REST_API_KEY"):
            return (
                "KAKAO_REST_API_KEY가 설정되지 않았습니다.\n"
                "카카오 개발자 센터(https://developers.kakao.com)에서 "
                "앱을 등록하고 REST API 키를 .env에 추가하세요.\n"
                "예: KAKAO_REST_API_KEY=your-kakao-rest-api-key"
            )

        size = min(int(kwargs.get("size", 10)), 50)
        sort = kwargs.get("sort", "accuracy")  # accuracy(정확도) / recency(최신)
        page = int(kwargs.get("page", 1))

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                KAKAO_SEARCH_API,
                headers=self._headers,
                params={
                    "query": query,
                    "size": str(size),
                    "sort": sort,
                    "page": str(page),
                },
            )

            if resp.status_code == 401:
                return (
                    "카카오 API 인증 실패 (401). "
                    "KAKAO_REST_API_KEY가 올바른지 확인하세요."
                )

            if resp.status_code != 200:
                error_msg = resp.text
                logger.error("[DaumCafe] 검색 실패 (%d): %s", resp.status_code, error_msg)
                return f"카카오 API 오류 ({resp.status_code}): {error_msg}"

            data = resp.json()

        meta = data.get("meta", {})
        documents = data.get("documents", [])
        total = meta.get("total_count", 0)

        if not documents:
            return f"'{query}' 검색 결과가 없습니다."

        # 검색 결과를 정리
        results = []
        for i, doc in enumerate(documents, 1):
            title = self._strip_html(doc.get("title", ""))
            contents = self._strip_html(doc.get("contents", ""))
            cafe_name = doc.get("cafename", "")
            url = doc.get("url", "")
            datetime_str = doc.get("datetime", "")[:10]  # YYYY-MM-DD

            results.append(
                f"[{i}] {title}\n"
                f"    카페: {cafe_name}\n"
                f"    요약: {contents}\n"
                f"    날짜: {datetime_str}\n"
                f"    링크: {url}"
            )

        sort_label = "정확도순" if sort == "accuracy" else "최신순"
        search_text = (
            f"검색어: '{query}' | 총 {total:,}건 중 {len(documents)}건 표시\n"
            f"정렬: {sort_label}\n\n"
            + "\n\n".join(results)
        )

        # LLM으로 검색 결과 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 시장조사 리서치 어시스턴트입니다.\n"
                "다음 카페 검색 결과를 분석하여 다음을 정리하세요:\n"
                "1. 핵심 트렌드/의견 요약 (3~5줄)\n"
                "2. 주요 키워드/토픽 분류\n"
                "3. 소비자 반응/분위기 분석 (긍정/부정/중립)\n"
                "4. 시장조사에 유용한 인사이트\n"
                "출처(카페명)를 명시하세요."
            ),
            user_prompt=search_text,
        )

        return f"## 다음 카페 검색 결과\n\n{search_text}\n\n---\n\n## 분석\n\n{analysis}"

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
            return (
                f"페이지 접근 실패 (HTTP {resp.status_code}). "
                "비공개 글이거나 로그인이 필요할 수 있습니다."
            )

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
                "다음 카페 글을 읽고 다음을 정리하세요:\n"
                "1. 글의 핵심 내용 요약 (3~5줄)\n"
                "2. 주요 키워드\n"
                "3. 시장조사에 유용한 포인트\n"
                "4. 글쓴이의 의견/감정 톤 분석"
            ),
            user_prompt=f"URL: {url}\n\n본문:\n{body_text}",
        )

        return f"## 카페 글 읽기\n\nURL: {url}\n\n### 본문\n{body_text}\n\n---\n\n### 분석\n{analysis}"

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

        # 다음 카페 본문 영역 추출 시도
        patterns = [
            r'class="article_viewer"[^>]*>(.*?)</div>',
            r'class="txt_sub"[^>]*>(.*?)</div>',
            r'id="postContent"[^>]*>(.*?)</div>',
            r'class="view_content"[^>]*>(.*?)</div>',
            r'class="article_view"[^>]*>(.*?)</div>',
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
