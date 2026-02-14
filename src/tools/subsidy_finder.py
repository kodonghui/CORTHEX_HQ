"""
정부 지원금/보조금 찾기 Tool.

기업마당, K-Startup 등에서 받을 수 있는 정부 지원사업을 자동 검색하고,
우리 회사 조건에 맞는 지원사업을 필터링하여 추천합니다.

사용 방법:
  - action="search": 지원사업 검색
  - action="detail": 특정 지원사업 상세 정보
  - action="match": 우리 회사 조건에 맞는 지원사업 필터링

필요 환경변수: 없음
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.subsidy_finder")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# 기업마당 RSS 피드
BIZINFO_RSS_URL = "https://www.bizinfo.go.kr/uss/rss/bizRssList.do"
# 기업마당 검색 (웹)
BIZINFO_SEARCH_URL = "https://www.bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/list.do"


class SubsidyFinderTool(BaseTool):
    """정부 지원사업 검색 및 매칭 도구."""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "search")

        if action == "search":
            return await self._search_subsidies(kwargs)
        elif action == "detail":
            return await self._get_detail(kwargs)
        elif action == "match":
            return await self._match_company(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}. "
                "search, detail, match 중 하나를 사용하세요."
            )

    # ── 지원사업 검색 ──

    async def _search_subsidies(self, kwargs: dict[str, Any]) -> str:
        keyword = kwargs.get("keyword", "").strip()
        if not keyword:
            return "검색 키워드(keyword)를 입력해주세요. 예: keyword='AI 교육 스타트업'"

        category = kwargs.get("category", "전체")
        region = kwargs.get("region", "전국")
        count = min(int(kwargs.get("count", 20)), 50)

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return (
                "beautifulsoup4 라이브러리가 필요합니다.\n"
                "```\npip install beautifulsoup4\n```"
            )

        results = []

        # 1) 기업마당 RSS 피드에서 검색
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(
                    BIZINFO_RSS_URL,
                    headers={"User-Agent": USER_AGENT},
                    timeout=20,
                )
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    items = soup.find_all("item")

                    for item in items[:count]:
                        title = item.find("title")
                        link = item.find("link")
                        desc = item.find("description")

                        title_text = title.get_text(strip=True) if title else ""
                        link_text = link.get_text(strip=True) if link else ""
                        desc_text = desc.get_text(strip=True) if desc else ""

                        # 키워드 필터
                        if keyword.lower() in title_text.lower() or keyword.lower() in desc_text.lower():
                            results.append({
                                "title": title_text,
                                "link": link_text,
                                "description": desc_text[:200],
                            })
        except Exception as e:
            logger.warning("기업마당 RSS 조회 실패: %s", e)

        # 2) 기업마당 웹 검색 (추가 결과)
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(
                    BIZINFO_SEARCH_URL,
                    params={"searchtxt": keyword},
                    headers={"User-Agent": USER_AGENT},
                    timeout=20,
                )
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")

                    # 지원사업 목록 파싱
                    rows = soup.select("table tbody tr, .tbl_list tbody tr, .list_tbl tbody tr")
                    for row in rows[:count]:
                        cols = row.find_all("td")
                        if len(cols) >= 2:
                            title_el = cols[0].find("a") or cols[1].find("a")
                            title_text = title_el.get_text(strip=True) if title_el else cols[0].get_text(strip=True)
                            link_href = title_el["href"] if title_el and title_el.get("href") else ""

                            # 중복 제거
                            if not any(r["title"] == title_text for r in results):
                                results.append({
                                    "title": title_text,
                                    "link": link_href if link_href.startswith("http") else "",
                                    "description": " | ".join(
                                        c.get_text(strip=True) for c in cols[1:4]
                                    ),
                                })
        except Exception as e:
            logger.warning("기업마당 웹 검색 실패: %s", e)

        await asyncio.sleep(1)  # 요청 간 딜레이

        if not results:
            return (
                f"'{keyword}' 관련 지원사업을 찾지 못했습니다.\n"
                "다른 키워드로 검색하거나, 기업마당(https://www.bizinfo.go.kr)을 "
                "직접 방문해보세요."
            )

        # 결과 정리
        result_lines = []
        for i, r in enumerate(results[:count], 1):
            result_lines.append(
                f"**{i}. {r['title']}**\n"
                f"   {r['description']}\n"
                f"   링크: {r['link']}" if r['link'] else
                f"**{i}. {r['title']}**\n"
                f"   {r['description']}"
            )

        report = (
            f"## 정부 지원사업 검색 결과\n\n"
            f"- **검색 키워드**: {keyword}\n"
            f"- **분류**: {category}\n"
            f"- **지역**: {region}\n"
            f"- **검색 결과**: {len(results)}건\n\n"
            + "\n\n".join(result_lines)
        )

        # LLM 분석
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 정부 지원사업 컨설턴트입니다.\n"
                "검색된 지원사업을 분석하여 다음을 정리하세요:\n"
                "1. 가장 유망한 지원사업 TOP 3 추천\n"
                "2. 각 지원사업의 지원 규모 및 자격 조건 (알 수 있는 범위 내)\n"
                "3. 신청 전략 및 준비 사항\n"
                "4. 주의사항 (마감일, 제한 조건 등)\n"
                "한국어로 간결하게 보고하세요."
            ),
            user_prompt=report,
        )

        return f"{report}\n\n---\n\n### 분석 및 추천\n\n{analysis}"

    # ── 지원사업 상세 ──

    async def _get_detail(self, kwargs: dict[str, Any]) -> str:
        url = kwargs.get("url", "").strip()
        if not url:
            return "지원사업 상세 페이지 URL을 입력해주세요."

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return "beautifulsoup4 라이브러리가 필요합니다.\n```\npip install beautifulsoup4\n```"

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=20,
                )
        except httpx.HTTPError as e:
            return f"페이지 접근 실패: {e}"

        if resp.status_code != 200:
            return f"페이지 접근 실패 (HTTP {resp.status_code})"

        soup = BeautifulSoup(resp.text, "html.parser")

        # script/style 제거
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        # 본문 텍스트 추출
        body = soup.body
        text = body.get_text(separator="\n", strip=True) if body else ""
        text = re.sub(r"\n{3,}", "\n\n", text)

        if len(text) < 50:
            return "페이지 본문을 추출할 수 없습니다."

        text = text[:6000]

        # LLM으로 정리
        analysis = await self._llm_call(
            system_prompt=(
                "당신은 정부 지원사업 분석 전문가입니다.\n"
                "지원사업 상세 페이지 내용을 정리하여 다음 항목으로 구분하세요:\n"
                "1. 사업명\n"
                "2. 지원 기관\n"
                "3. 지원 규모 (금액)\n"
                "4. 지원 대상 (자격 조건)\n"
                "5. 신청 기간\n"
                "6. 지원 내용 상세\n"
                "7. 신청 방법\n"
                "8. 참고 사항\n"
                "알 수 없는 항목은 '확인 필요'로 표시하세요.\n"
                "한국어로 정리하세요."
            ),
            user_prompt=f"URL: {url}\n\n페이지 내용:\n{text}",
        )

        return f"## 지원사업 상세 정보\n\nURL: {url}\n\n{analysis}"

    # ── 회사 조건 매칭 ──

    async def _match_company(self, kwargs: dict[str, Any]) -> str:
        company_type = kwargs.get("company_type", "").strip()
        industry = kwargs.get("industry", "").strip()

        if not company_type and not industry:
            return (
                "회사 조건을 입력해주세요.\n"
                "예: company_type='창업3년이내', industry='교육'\n"
                "company_type 옵션: 예비창업자, 창업3년이내, 창업7년이내, 중소기업\n"
                "industry 옵션: 교육, IT, 서비스, 제조, 바이오 등"
            )

        # 조건에 맞는 키워드로 검색
        search_keywords = []
        if company_type:
            search_keywords.append(company_type)
        if industry:
            search_keywords.append(industry)
        search_keywords.append("지원사업")

        combined_keyword = " ".join(search_keywords)

        # 검색 실행
        search_result = await self._search_subsidies({
            "keyword": combined_keyword,
            "count": 30,
        })

        # 추가 LLM 매칭 분석
        match_analysis = await self._llm_call(
            system_prompt=(
                "당신은 정부 지원사업 매칭 전문가입니다.\n"
                "아래 회사 조건에 맞는 지원사업을 추천하세요:\n"
                "1. 회사 조건에 가장 적합한 지원사업 순서대로 정렬\n"
                "2. 각 지원사업별 적합도 (높음/중간/낮음)\n"
                "3. 우선 신청해야 할 지원사업 TOP 3\n"
                "4. 신청 준비 로드맵 (시간순)\n"
                "한국어로 보고하세요."
            ),
            user_prompt=(
                f"## 회사 조건\n"
                f"- 기업 유형: {company_type or '미지정'}\n"
                f"- 업종: {industry or '미지정'}\n\n"
                f"## 검색된 지원사업\n{search_result}"
            ),
        )

        return (
            f"## 우리 회사 맞춤 지원사업 추천\n\n"
            f"- **기업 유형**: {company_type or '미지정'}\n"
            f"- **업종**: {industry or '미지정'}\n\n"
            f"---\n\n{match_analysis}"
        )
